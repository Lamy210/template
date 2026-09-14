from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
HOMEBREW_WORKFLOW = REPO_ROOT / ".github/workflows/reusable-homebrew-update.yml"
PUBLISHER_EXAMPLE = REPO_ROOT / "examples/app-release-publisher.yml"


class HomebrewPublisherWorkflowContractTests(unittest.TestCase):
    def homebrew_text(self) -> str:
        return HOMEBREW_WORKFLOW.read_text(encoding="utf-8")

    def publisher_text(self) -> str:
        return PUBLISHER_EXAMPLE.read_text(encoding="utf-8")

    def test_homebrew_requires_validated_source_tag(self) -> None:
        text = self.homebrew_text()
        self.assertIn("source_tag:", text)
        self.assertIn("SOURCE_TAG: ${{ inputs.source_tag }}", text)
        self.assertIn('gh release download "${SOURCE_TAG}"', text)

    def test_homebrew_never_derives_release_identity_from_github_ref(self) -> None:
        text = self.homebrew_text()
        for forbidden in ("github.ref_name", "GITHUB_REF_NAME", "GITHUB_REF_TYPE"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_homebrew_checks_out_trusted_publisher_sha(self) -> None:
        text = self.homebrew_text()
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("persist-credentials: false", text)

    def test_publisher_runs_homebrew_only_after_sign_and_publish(self) -> None:
        text = self.publisher_text()
        self.assertIn("  homebrew:", text)
        self.assertIn("needs: [validate, sign-and-publish]", text)
        self.assertIn("uses: ./.github/workflows/reusable-homebrew-update.yml", text)
        self.assertIn("source_tag: ${{ needs.validate.outputs.source_tag }}", text)
        self.assertIn("tap_token: ${{ secrets.HOMEBREW_TAP_TOKEN }}", text)


if __name__ == "__main__":
    unittest.main()
