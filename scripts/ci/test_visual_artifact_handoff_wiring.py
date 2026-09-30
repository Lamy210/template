from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
E2E = ROOT / ".github/workflows/reusable-macos-e2e.yml"
VISUAL = ROOT / ".github/workflows/reusable-visual-regression.yml"
TESTS = ROOT / ".github/workflows/tests.yml"
ADOPTION = ROOT / ".github/workflows/test-profile-adoption.yml"


class VisualArtifactHandoffWiringTests(unittest.TestCase):
    def test_e2e_exports_exact_visual_artifact_identity(self) -> None:
        text = E2E.read_text(encoding="utf-8")
        for token in (
            "visual_artifact_id:",
            "visual_artifact_digest:",
            "visual_artifact_name:",
            "steps.visual_upload.outputs.artifact-id",
            "steps.visual_upload.outputs.artifact-digest",
            "macos-e2e-visual-${{ github.run_id }}-${{ github.run_attempt }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_visual_consumer_validates_then_downloads_by_exact_id(self) -> None:
        text = VISUAL.read_text(encoding="utf-8")
        identity = text.index("- name: Validate current visual artifact identity")
        download = text.index("- name: Download current visual capture")
        self.assertLess(identity, download)
        for token in (
            "current_artifact_id:",
            "current_artifact_digest:",
            "current_run_artifact_identity.py",
            "artifact-ids: ${{ inputs.current_artifact_id }}",
            "merge-multiple: true",
            "ARTIFACT_IDENTITY_OUTCOME: ${{ steps.artifact_identity.outcome }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
        download_block = text[download:text.index("- name: Validate visual manifest", download)]
        self.assertNotIn("name: ${{ inputs.current_artifact_name }}", download_block)

    def test_tests_workflow_forwards_e2e_artifact_identity(self) -> None:
        text = TESTS.read_text(encoding="utf-8")
        for token in (
            "current_artifact_id: ${{ needs.e2e-run.outputs.visual_artifact_id }}",
            "current_artifact_digest: ${{ needs.e2e-run.outputs.visual_artifact_digest }}",
            "current_artifact_name: ${{ needs.e2e-run.outputs.visual_artifact_name }}",
            "CURRENT_ARTIFACT_ID: ${{ needs.e2e-run.outputs.visual_artifact_id }}",
            "Validate verified current visual capture identity",
            "current_run_artifact_identity.py",
            "artifact-ids: ${{ needs.e2e-run.outputs.visual_artifact_id }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

    def test_adoption_visual_flow_forwards_e2e_artifact_identity(self) -> None:
        text = ADOPTION.read_text(encoding="utf-8")
        for token in (
            "current_artifact_id: ${{ needs.macos-app-e2e.outputs.visual_artifact_id }}",
            "current_artifact_digest: ${{ needs.macos-app-e2e.outputs.visual_artifact_digest }}",
            "current_artifact_name: ${{ needs.macos-app-e2e.outputs.visual_artifact_name }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
