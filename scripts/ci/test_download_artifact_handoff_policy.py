from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.download_artifact_handoff_policy import (
    parse_download_artifact_steps,
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class DownloadArtifactHandoffPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path("fixture.yml"), body)

    def test_exact_artifact_id_is_allowed(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download exact
        uses: actions/download-artifact@deadbeef
        with:
          artifact-ids: ${{ needs.build.outputs.artifact_id }}
          path: output
"""
        )
        self.assertEqual([], violations)

    def test_attempt_scoped_name_is_allowed(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download diagnostics
        uses: actions/download-artifact@deadbeef
        with:
          name: diagnostics-${{ github.run_attempt }}
          path: output
"""
        )
        self.assertEqual([], violations)

    def test_stable_name_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download stale-prone
        uses: actions/download-artifact@deadbeef
        with:
          name: diagnostics
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("stable across workflow reruns", violations[0].message)

    def test_run_id_without_attempt_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download stale-prone
        uses: actions/download-artifact@deadbeef
        with:
          name: diagnostics-${{ github.run_id }}
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("github.run_attempt", violations[0].message)

    def test_pattern_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download broad
        uses: actions/download-artifact@deadbeef
        with:
          pattern: diagnostics-*
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("pattern selection is not exact", violations[0].message)

    def test_missing_selector_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download all
        uses: actions/download-artifact@deadbeef
        with:
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("must select", violations[0].message)

    def test_quoted_action_and_unnamed_step_are_detected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - uses: "actions/download-artifact@deadbeef"
        with:
          name: fixed-name
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertEqual("<unnamed download-artifact step>", violations[0].step_name)

    def test_parser_keeps_separate_download_steps(self) -> None:
        steps = parse_download_artifact_steps(
            Path("fixture.yml"),
            """
jobs:
  test:
    steps:
      - name: Exact
        uses: actions/download-artifact@deadbeef
        with:
          artifact-ids: 123
          path: one
      - name: Scoped
        uses: actions/download-artifact@deadbeef
        with:
          name: second-${{ github.run_attempt }}
          path: two
""",
        )
        self.assertEqual(["Exact", "Scoped"], [step.step_name for step in steps])
        self.assertEqual(["123", None], [step.artifact_ids for step in steps])

    def test_repository_download_artifacts_follow_handoff_policy(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual(
            [],
            violations,
            "\n".join(
                f"{item.path}:{item.line}: {item.step_name}: {item.message}"
                for item in violations
            ),
        )


if __name__ == "__main__":
    unittest.main()
