from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.download_artifact_identity_policy import (
    parse_download_artifact_steps,
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class DownloadArtifactIdentityPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path("fixture.yml"), body)

    def test_accepts_exact_artifact_ids(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download exact artifact
        uses: actions/download-artifact@deadbeef
        with:
          artifact-ids: ${{ needs.build.outputs.artifact_id }}
          path: output
          merge-multiple: true
"""
        )
        self.assertEqual([], violations)

    def test_rejects_name_lookup(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Download by name
        uses: actions/download-artifact@deadbeef
        with:
          name: trusted-output
          path: output
"""
        )
        self.assertEqual(2, len(violations))
        self.assertTrue(any("artifact-ids" in item.message for item in violations))
        self.assertTrue(any("name selector" in item.message for item in violations))

    def test_rejects_pattern_lookup(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - uses: actions/download-artifact@deadbeef
        with:
          pattern: output-*
"""
        )
        self.assertEqual(2, len(violations))
        self.assertTrue(any("pattern selector" in item.message for item in violations))

    def test_rejects_empty_or_missing_artifact_ids(self) -> None:
        for body in (
            """
steps:
  - uses: actions/download-artifact@deadbeef
    with:
      artifact-ids:
      path: output
""",
            """
steps:
  - uses: actions/download-artifact@deadbeef
    with:
      path: output
""",
        ):
            with self.subTest(body=body):
                violations = self.validate(body)
                self.assertEqual(1, len(violations))
                self.assertIn("artifact-ids", violations[0].message)

    def test_parses_quoted_action_reference(self) -> None:
        steps = parse_download_artifact_steps(
            Path("fixture.yml"),
            """
jobs:
  test:
    steps:
      - name: Exact
        uses: 'actions/download-artifact@deadbeef'
        with:
          artifact-ids: 12345
""",
        )
        self.assertEqual(1, len(steps))
        self.assertEqual("Exact", steps[0].step_name)
        self.assertEqual("12345", steps[0].artifact_ids)

    def test_quoted_keys_cannot_bypass_download_identity_policy(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - "uses": actions/download-artifact@deadbeef
        "with":
          "name": trusted-output
          "path": output
"""
        )
        self.assertEqual(2, len(violations))
        self.assertTrue(any("artifact-ids" in item.message for item in violations))
        self.assertTrue(any("name selector" in item.message for item in violations))

    def test_repository_has_no_name_or_pattern_downloads(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
