from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SWIFT_TESTS = ROOT / ".github/workflows/reusable-swift-tests.yml"
TESTS = ROOT / ".github/workflows/tests.yml"
VISUAL = ROOT / ".github/workflows/reusable-visual-regression.yml"


def step_block(text: str, name: str) -> str:
    marker = f"      - name: {name}\n"
    if marker not in text:
        return ""
    tail = text.split(marker, 1)[1]
    next_step = tail.find("\n      - name: ")
    body = tail if next_step < 0 else tail[:next_step]
    return marker + body


class TrustedBaselineArtifactWiringTests(unittest.TestCase):
    def test_coverage_baseline_replaces_prior_rerun_attempt_artifact(self) -> None:
        text = SWIFT_TESTS.read_text(encoding="utf-8")
        block = step_block(text, "Publish trusted main coverage baseline")

        self.assertTrue(block)
        self.assertIn("actions/upload-artifact@", block)
        self.assertIn("name: ${{ inputs.coverage_artifact_name }}", block)
        self.assertIn("retention-days: 90", block)
        self.assertIn("overwrite: true", block)

    def test_coverage_baseline_publishes_and_validates_attempt_provenance(self) -> None:
        text = SWIFT_TESTS.read_text(encoding="utf-8")
        export = step_block(text, "Export normalized coverage")
        provenance = step_block(text, "Build trusted coverage baseline provenance")
        compare = step_block(text, "Resolve and compare trusted coverage baseline")
        publish = step_block(text, "Publish trusted main coverage baseline")

        self.assertTrue(export)
        self.assertNotIn("coverage-baseline-provenance.json", export)

        self.assertTrue(provenance)
        for token in (
            "SOURCE_REPOSITORY_ID: ${{ github.repository_id }}",
            "SOURCE_RUN_ID: ${{ github.run_id }}",
            "SOURCE_RUN_ATTEMPT: ${{ github.run_attempt }}",
            "coverage-baseline-provenance.json",
            '"runAttempt": run_attempt',
            'echo "path=${provenance}"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, provenance)

        self.assertTrue(compare)
        self.assertIn("validate-coverage-baseline-provenance.py", compare)
        self.assertIn("--resolver-metadata", compare)
        self.assertIn("--baseline-provenance", compare)
        self.assertIn("--baseline-summary", compare)

        self.assertTrue(publish)
        self.assertIn("${{ steps.coverage.outputs.summary }}", publish)
        self.assertIn("${{ steps.coverage_provenance.outputs.path }}", publish)

    def test_visual_baseline_replaces_prior_rerun_attempt_artifact(self) -> None:
        text = TESTS.read_text(encoding="utf-8")
        block = step_block(text, "Publish trusted rolling baseline")

        self.assertTrue(block)
        self.assertIn("actions/upload-artifact@", block)
        self.assertIn("name: ${{ env.BASELINE_ARTIFACT_NAME }}", block)
        self.assertIn("retention-days: 90", block)
        self.assertIn("overwrite: true", block)

    def test_attempt_scoped_diagnostic_artifacts_remain_append_only(self) -> None:
        swift = SWIFT_TESTS.read_text(encoding="utf-8")
        visual = VISUAL.read_text(encoding="utf-8")

        coverage = step_block(swift, "Upload PR coverage diagnostics")
        report = step_block(visual, "Upload visual comparison report")

        self.assertTrue(coverage)
        self.assertIn("github.run_attempt", coverage)
        self.assertNotIn("overwrite: true", coverage)

        self.assertTrue(report)
        self.assertIn("github.run_attempt", report)
        self.assertNotIn("overwrite: true", report)


if __name__ == "__main__":
    unittest.main()
