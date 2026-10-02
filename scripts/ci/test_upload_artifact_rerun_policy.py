from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.upload_artifact_rerun_policy import (
    parse_upload_artifact_steps,
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class UploadArtifactRerunPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path("fixture.yml"), body)

    def test_attempt_scoped_name_is_allowed(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Upload diagnostics
        uses: actions/upload-artifact@deadbeef
        with:
          name: diagnostics-${{ github.run_id }}-${{ github.run_attempt }}
          path: output
"""
        )
        self.assertEqual([], violations)

    def test_explicit_overwrite_is_allowed_for_stable_name(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Publish rolling baseline
        uses: actions/upload-artifact@deadbeef
        with:
          name: rolling-baseline
          path: output
          overwrite: true
"""
        )
        self.assertEqual([], violations)

    def test_literal_run_attempt_text_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Upload diagnostics
        uses: actions/upload-artifact@deadbeef
        with:
          name: diagnostics-github.run_attempt
          path: output
"""
        )
        self.assertEqual(1, len(violations))

    def test_run_id_without_attempt_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Upload diagnostics
        uses: actions/upload-artifact@deadbeef
        with:
          name: diagnostics-${{ github.run_id }}
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("github.run_attempt", violations[0].message)

    def test_mixed_case_upload_action_cannot_bypass_policy(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Mixed case upload
        uses: Actions/Upload-Artifact@deadbeef
        with:
          name: fixed-name
          path: output
"""
        )
        self.assertEqual(1, len(violations), violations)
        self.assertIn("github.run_attempt", violations[0].message)

    def test_deeply_indented_upload_inputs_are_parsed(self) -> None:
        body = """
jobs:
  test:
    steps:
      - uses: actions/upload-artifact@deadbeef
        with:
            name: diagnostics-${{ github.run_attempt }}
            path: output
"""
        self.assertEqual([], self.validate(body))
        steps = parse_upload_artifact_steps(Path("fixture.yml"), body)
        self.assertEqual(
            "diagnostics-${{ github.run_attempt }}",
            steps[0].artifact_name,
        )

    def test_quoted_upload_action_is_still_detected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Quoted upload
        uses: "actions/upload-artifact@deadbeef"
        with:
          name: fixed-name
          path: output
"""
        )
        self.assertEqual(1, len(violations))

    def test_unnamed_upload_step_is_still_detected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - uses: actions/upload-artifact@deadbeef
        with:
          name: fixed-name
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertEqual("<unnamed upload-artifact step>", violations[0].step_name)

    def test_unnamed_attempt_scoped_upload_is_allowed(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - uses: actions/upload-artifact@deadbeef
        with:
          name: diagnostics-${{ github.run_attempt }}
          path: output
"""
        )
        self.assertEqual([], violations)

    def test_upload_does_not_borrow_later_job_inputs(self) -> None:
        body = """
jobs:
  upload-job:
    steps:
      - uses: actions/upload-artifact@deadbeef
  reusable-job:
    uses: ./.github/workflows/reusable.yml
    with:
      name: diagnostics-${{ github.run_attempt }}
      overwrite: true
"""
        violations = self.validate(body)
        self.assertEqual(1, len(violations))
        self.assertIn("explicit name", violations[0].message)

        steps = parse_upload_artifact_steps(Path("fixture.yml"), body)
        self.assertIsNone(steps[0].artifact_name)
        self.assertIsNone(steps[0].overwrite)

    def test_missing_name_is_rejected(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - name: Upload diagnostics
        uses: actions/upload-artifact@deadbeef
        with:
          path: output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("explicit name", violations[0].message)

    def test_false_or_dynamic_overwrite_does_not_bypass_policy(self) -> None:
        for overwrite in ("false", "${{ inputs.overwrite }}"):
            with self.subTest(overwrite=overwrite):
                violations = self.validate(
                    f"""
jobs:
  test:
    steps:
      - name: Upload diagnostics
        uses: actions/upload-artifact@deadbeef
        with:
          name: fixed-name
          path: output
          overwrite: {overwrite}
"""
                )
                self.assertEqual(1, len(violations))

    def test_parser_keeps_separate_upload_steps(self) -> None:
        steps = parse_upload_artifact_steps(
            Path("fixture.yml"),
            """
jobs:
  test:
    steps:
      - name: First upload
        uses: actions/upload-artifact@deadbeef
        with:
          name: first-${{ github.run_attempt }}
          path: one
      - name: Second upload
        uses: actions/upload-artifact@deadbeef
        with:
          name: second
          path: two
          overwrite: true
""",
        )
        self.assertEqual(["First upload", "Second upload"], [step.step_name for step in steps])
        self.assertEqual(
            ["first-${{ github.run_attempt }}", "second"],
            [step.artifact_name for step in steps],
        )

    def test_quoted_keys_cannot_bypass_upload_rerun_policy(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    steps:
      - "uses": actions/upload-artifact@deadbeef
        "with":
          "name": fixed-name
          "path": output
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("github.run_attempt", violations[0].message)

    def test_repository_upload_artifacts_follow_rerun_policy(self) -> None:
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
