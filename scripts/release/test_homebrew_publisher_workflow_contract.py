from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
HOMEBREW_WORKFLOW = REPO_ROOT / ".github/workflows/reusable-homebrew-update.yml"
PUBLISHER_EXAMPLE = REPO_ROOT / "examples/app-release-publisher.yml"


def step_block(text: str, step_name: str) -> str:
    marker = f"      - name: {step_name}\n"
    start = text.find(marker)
    if start < 0:
        return ""
    next_step = text.find("\n      - name: ", start + len(marker))
    return text[start:] if next_step < 0 else text[start:next_step]


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

    def test_homebrew_rejects_noncanonical_stable_release_tags(self) -> None:
        block = step_block(self.homebrew_text(), "Validate release identity and inputs")
        self.assertTrue(block)
        self.assertIn(
            r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
            block,
        )
        self.assertNotIn(r"^v[0-9]+\.[0-9]+\.[0-9]+$", block)

    def test_homebrew_validates_tap_default_branch_before_secret_use(self) -> None:
        block = step_block(self.homebrew_text(), "Validate release identity and inputs")
        self.assertTrue(block)
        self.assertIn("TAP_DEFAULT_BRANCH: ${{ inputs.tap_default_branch }}", block)
        self.assertIn('git check-ref-format --branch "${TAP_DEFAULT_BRANCH}"', block)
        self.assertNotIn("secrets.tap_token", block)

    def test_homebrew_never_derives_release_identity_from_github_ref(self) -> None:
        text = self.homebrew_text()
        for forbidden in ("github.ref_name", "GITHUB_REF_NAME", "GITHUB_REF_TYPE"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_homebrew_checks_out_trusted_publisher_sha(self) -> None:
        text = self.homebrew_text()
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("persist-credentials: false", text)

    def test_tap_token_is_available_only_to_steps_that_need_tap_network_access(self) -> None:
        text = self.homebrew_text()
        for step_name in (
            "Clone tap repository",
            "Prepare tap update branch",
            "Commit and push Cask branch",
            "Open or reuse tap pull request",
        ):
            with self.subTest(step_name=step_name):
                block = step_block(text, step_name)
                self.assertTrue(block, f"missing step: {step_name}")
                self.assertIn("GH_TOKEN: ${{ secrets.tap_token }}", block)

        for step_name in (
            "Validate release identity and inputs",
            "Checkout trusted publisher automation",
            "Download published checksum",
            "Render Cask",
        ):
            with self.subTest(step_name=step_name):
                block = step_block(text, step_name)
                self.assertTrue(block, f"missing step: {step_name}")
                self.assertNotIn("secrets.tap_token", block)

    def test_publisher_runs_homebrew_only_after_sign_and_publish(self) -> None:
        text = self.publisher_text()
        self.assertIn("  homebrew:", text)
        self.assertIn("needs: [validate, sign-and-publish]", text)
        self.assertIn("uses: ./.github/workflows/reusable-homebrew-update.yml", text)
        self.assertIn("source_tag: ${{ needs.validate.outputs.source_tag }}", text)
        self.assertIn("tap_token: ${{ secrets.HOMEBREW_TAP_TOKEN }}", text)


if __name__ == "__main__":
    unittest.main()
