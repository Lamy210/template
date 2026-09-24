from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
HOMEBREW_WORKFLOW = REPO_ROOT / ".github/workflows/reusable-homebrew-update.yml"
PUBLISHER_EXAMPLE = REPO_ROOT / "examples/app-release-publisher.yml"
BUILD_EXAMPLE = REPO_ROOT / "examples/app-release-build.yml"
REUSABLE_RELEASE = REPO_ROOT / ".github/workflows/reusable-macos-release.yml"


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

    def test_homebrew_validates_tap_repository_components_before_secret_use(self) -> None:
        block = step_block(self.homebrew_text(), "Validate release identity and inputs")
        self.assertTrue(block)
        self.assertIn("TAP_REPOSITORY: ${{ inputs.tap_repository }}", block)
        self.assertIn(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", block)
        self.assertIn('tap_owner="${TAP_REPOSITORY%%/*}"', block)
        self.assertIn('tap_name="${TAP_REPOSITORY#*/}"', block)
        self.assertIn('"${tap_owner}" == "."', block)
        self.assertIn('"${tap_owner}" == ".."', block)
        self.assertIn('"${tap_name}" == "."', block)
        self.assertIn('"${tap_name}" == ".."', block)
        self.assertNotIn("secrets.tap_token", block)

    def test_homebrew_validates_tap_default_branch_before_secret_use(self) -> None:
        block = step_block(self.homebrew_text(), "Validate release identity and inputs")
        self.assertTrue(block)
        self.assertIn("TAP_DEFAULT_BRANCH: ${{ inputs.tap_default_branch }}", block)
        self.assertIn('git check-ref-format --branch "${TAP_DEFAULT_BRANCH}"', block)
        self.assertNotIn("secrets.tap_token", block)

    def test_homebrew_requires_literal_dmg_asset_basename(self) -> None:
        block = step_block(self.homebrew_text(), "Validate release identity and inputs")
        self.assertTrue(block)
        self.assertIn(
            r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.dmg$",
            block,
        )

    def test_homebrew_never_derives_release_identity_from_github_ref(self) -> None:
        text = self.homebrew_text()
        for forbidden in ("github.ref_name", "GITHUB_REF_NAME", "GITHUB_REF_TYPE"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_homebrew_checks_out_trusted_publisher_sha(self) -> None:
        text = self.homebrew_text()
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("persist-credentials: false", text)

    def test_published_assets_are_rebound_before_cask_render(self) -> None:
        block = step_block(self.homebrew_text(), "Download and verify published release assets")
        self.assertTrue(block)
        self.assertIn('gh release view "${SOURCE_TAG}"', block)
        self.assertIn("--json assets,isDraft,isPrerelease,tagName", block)
        self.assertIn("source/scripts/release/verify-release-state.py", block)
        self.assertIn("--metadata release-assets/release.json", block)
        self.assertIn('--asset "${DMG_NAME}"', block)
        self.assertIn('--asset "${DMG_NAME}.sha256"', block)
        self.assertIn("--asset release-provenance.json", block)
        self.assertIn('"${DMG_NAME}" "${DMG_NAME}.sha256" release-provenance.json', block)
        self.assertIn("source/scripts/release/verify-published-release-assets.py", block)
        self.assertIn('--dmg "release-assets/${DMG_NAME}"', block)
        self.assertIn('--checksum "release-assets/${DMG_NAME}.sha256"', block)
        self.assertIn("--provenance release-assets/release-provenance.json", block)
        self.assertIn('--tag "${SOURCE_TAG}"', block)
        self.assertIn('--repository "${EXPECTED_REPOSITORY}"', block)
        self.assertIn('--publisher-sha "${EXPECTED_PUBLISHER_SHA}"', block)
        self.assertIn("--source-sha-output release-assets/source-sha.txt", block)
        self.assertIn('echo "SHA256=${sha256}" >>"${GITHUB_ENV}"', block)
        self.assertIn('echo "source_sha=${source_sha}" >>"${GITHUB_OUTPUT}"', block)
        self.assertNotIn("source/scripts/release/release_checksum.py", block)

        self.assertLess(
            self.homebrew_text().index("Download and verify published release assets"),
            self.homebrew_text().index("Render Cask"),
        )

    def test_homebrew_rebinds_provenance_source_to_live_tag_and_trusted_history(self) -> None:
        text = self.homebrew_text()
        assets = text.index("Download and verify published release assets")
        rebind = text.index("Rebind published provenance to live release source")
        tap = text.index("Clone tap repository")
        self.assertLess(assets, rebind)
        self.assertLess(rebind, tap)

        block = step_block(text, "Rebind published provenance to live release source")
        self.assertTrue(block)
        self.assertIn("working-directory: source", block)
        self.assertIn("GH_TOKEN: ${{ github.token }}", block)
        self.assertIn("SOURCE_TAG: ${{ inputs.source_tag }}", block)
        self.assertIn(
            "SOURCE_SHA: ${{ steps.published_assets.outputs.source_sha }}",
            block,
        )
        self.assertIn("PUBLISHER_SHA: ${{ github.sha }}", block)
        self.assertIn("scripts/release/verify-release-source.sh", block)
        self.assertNotIn("secrets.tap_token", block)

    def test_rendered_cask_is_syntax_checked_before_tap_write(self) -> None:
        block = step_block(self.homebrew_text(), "Render Cask")
        self.assertTrue(block)
        self.assertIn('ruby -c "${OUTPUT_CASK}"', block)

    def test_tap_token_is_available_only_to_steps_that_need_tap_network_access(self) -> None:
        text = self.homebrew_text()
        for step_name in (
            "Clone tap repository",
            "Verify cloned tap repository identity",
            "Prepare tap update branch",
            "Commit and push Cask branch",
            "Open or reuse tap pull request",
            "Reverify tap branch and pull request identity",
        ):
            with self.subTest(step_name=step_name):
                block = step_block(text, step_name)
                self.assertTrue(block, f"missing step: {step_name}")
                self.assertIn("GH_TOKEN: ${{ secrets.tap_token }}", block)

        for step_name in (
            "Validate release identity and inputs",
            "Checkout trusted publisher automation",
            "Download and verify published release assets",
            "Rebind published provenance to live release source",
            "Render Cask",
        ):
            with self.subTest(step_name=step_name):
                block = step_block(text, step_name)
                self.assertTrue(block, f"missing step: {step_name}")
                self.assertNotIn("secrets.tap_token", block)

    def test_homebrew_rejects_repository_redirect_or_transfer_before_branch_operations(self) -> None:
        text = self.homebrew_text()
        clone = text.index("Clone tap repository")
        verify = text.index("Verify cloned tap repository identity")
        prepare = text.index("Prepare tap update branch")
        self.assertLess(clone, verify)
        self.assertLess(verify, prepare)

        block = step_block(text, "Verify cloned tap repository identity")
        self.assertTrue(block)
        self.assertIn("GH_TOKEN: ${{ secrets.tap_token }}", block)
        self.assertIn("TAP_REPOSITORY: ${{ inputs.tap_repository }}", block)
        self.assertIn('gh repo view "${TAP_REPOSITORY}"', block)
        self.assertIn("--json nameWithOwner,defaultBranchRef", block)
        self.assertIn(".nameWithOwner, .defaultBranchRef.name", block)
        self.assertIn(
            'if [[ "${canonical_repository,,}" != "${TAP_REPOSITORY,,}" ]]',
            block,
        )
        self.assertIn(
            "Tap repository resolved to a different canonical repository identity.",
            block,
        )
        self.assertNotIn("git push", block)
        self.assertNotIn("gh pr create", block)

    def test_homebrew_binds_configured_tap_default_to_canonical_repository_default(self) -> None:
        block = step_block(self.homebrew_text(), "Verify cloned tap repository identity")
        self.assertTrue(block)
        self.assertIn("TAP_DEFAULT_BRANCH: ${{ inputs.tap_default_branch }}", block)
        self.assertIn("--json nameWithOwner,defaultBranchRef", block)
        self.assertIn(".defaultBranchRef.name", block)
        self.assertIn(
            'if [[ "${canonical_default_branch}" != "${TAP_DEFAULT_BRANCH}" ]]',
            block,
        )
        self.assertIn(
            "Configured tap_default_branch does not match the canonical repository default branch.",
            block,
        )
        self.assertNotIn("git push", block)
        self.assertNotIn("gh pr create", block)

    def test_existing_automation_branch_is_rebuilt_from_trusted_tap_default(self) -> None:
        prepare = step_block(self.homebrew_text(), "Prepare tap update branch")
        push = step_block(self.homebrew_text(), "Commit and push Cask branch")
        self.assertTrue(prepare)
        self.assertTrue(push)

        self.assertIn('git switch -C "${branch}" "origin/${TAP_DEFAULT_BRANCH}"', prepare)
        self.assertNotIn('git switch -C "${branch}" "origin/${branch}"', prepare)
        self.assertIn('git ls-remote --exit-code --branches origin "refs/heads/${branch}"', prepare)
        self.assertIn("ls_remote_status=$?", prepare)
        self.assertIn('case "${ls_remote_status}" in', prepare)
        self.assertIn("    2)", prepare)
        self.assertIn("Failed to query existing automation branch from tap remote.", prepare)
        self.assertIn('remote_branch_sha=', prepare)
        self.assertIn('remote_branch_sha=${remote_branch_sha}', prepare)
        self.assertIn('remote_branch_ref', prepare)

        self.assertIn("REMOTE_BRANCH_SHA: ${{ steps.branch.outputs.remote_branch_sha }}", push)
        self.assertIn(
            '--force-with-lease="refs/heads/${BRANCH}:${REMOTE_BRANCH_SHA}"',
            push,
        )
        self.assertIn(
            '--force-with-lease="refs/heads/${BRANCH}:"',
            push,
        )
        self.assertIn('pushed_sha="$(git rev-parse HEAD)"', push)
        self.assertIn('echo "pushed_sha=${pushed_sha}" >>"${GITHUB_OUTPUT}"', push)

    def test_tap_pull_request_lookup_fails_closed_before_create(self) -> None:
        block = step_block(self.homebrew_text(), "Open or reuse tap pull request")
        self.assertTrue(block)
        self.assertIn("gh pr list", block)
        self.assertIn('--repo "${TAP_REPOSITORY}"', block)
        self.assertIn("--state open", block)
        self.assertIn('--head "${BRANCH}"', block)
        self.assertIn('--base "${TAP_DEFAULT_BRANCH}"', block)
        self.assertIn("--limit 100", block)
        self.assertIn(
            "--json number,headRefName,baseRefName,headRefOid,headRepository,headRepositoryOwner,isCrossRepository",
            block,
        )
        self.assertIn("Failed to query existing tap pull requests.", block)
        self.assertIn("source/scripts/homebrew/select-tap-pull-request.py", block)
        self.assertIn('--repository "${TAP_REPOSITORY}"', block)
        self.assertIn('--head "${BRANCH}"', block)
        self.assertIn('--base "${TAP_DEFAULT_BRANCH}"', block)
        self.assertIn('--head-sha "${PUSHED_SHA}"', block)
        self.assertIn("PUSHED_SHA: ${{ steps.push.outputs.pushed_sha }}", block)
        self.assertIn("Tap pull request query result failed identity validation.", block)
        self.assertNotIn('if gh pr view "${BRANCH}"', block)
        self.assertNotIn('gh pr view "${open_pr_number}"', block)
        self.assertGreaterEqual(block.count('open_pr_number="$(query_open_pr_number)"'), 2)
        self.assertLess(
            block.index("gh pr create"),
            block.rindex('open_pr_number="$(query_open_pr_number)"'),
        )
        self.assertIn("Tap pull request post-create identity validation failed.", block)

    def test_tap_pull_request_is_rebound_to_remote_branch_before_success(self) -> None:
        text = self.homebrew_text()
        open_step = step_block(text, "Open or reuse tap pull request")
        final_step = step_block(text, "Reverify tap branch and pull request identity")
        self.assertTrue(open_step)
        self.assertTrue(final_step)
        self.assertIn("id: pull_request", open_step)
        self.assertIn('echo "number=${open_pr_number}" >>"${GITHUB_OUTPUT}"', open_step)
        self.assertIn("GH_TOKEN: ${{ secrets.tap_token }}", final_step)
        self.assertIn("TAP_REPOSITORY: ${{ inputs.tap_repository }}", final_step)
        self.assertIn("TAP_DEFAULT_BRANCH: ${{ inputs.tap_default_branch }}", final_step)
        self.assertIn("--json nameWithOwner,defaultBranchRef", final_step)
        self.assertIn(".nameWithOwner, .defaultBranchRef.name", final_step)
        self.assertIn(
            'if [[ "${canonical_repository,,}" != "${TAP_REPOSITORY,,}" ]]',
            final_step,
        )
        self.assertIn(
            'if [[ "${canonical_default_branch}" != "${TAP_DEFAULT_BRANCH}" ]]',
            final_step,
        )
        self.assertIn(
            "Tap repository identity changed before final verification.",
            final_step,
        )
        self.assertIn(
            "Tap default branch changed before final verification.",
            final_step,
        )
        self.assertIn("PUSHED_SHA: ${{ steps.push.outputs.pushed_sha }}", final_step)
        self.assertIn("PR_NUMBER: ${{ steps.pull_request.outputs.number }}", final_step)
        self.assertIn('git ls-remote --exit-code --branches origin "refs/heads/${BRANCH}"', final_step)
        self.assertIn('if [[ "${remote_sha}" != "${PUSHED_SHA}" ]]', final_step)
        self.assertIn("Automation branch moved after the trusted push.", final_step)
        self.assertIn("source/scripts/homebrew/select-tap-pull-request.py", final_step)
        self.assertIn('--head-sha "${PUSHED_SHA}"', final_step)
        self.assertIn('if [[ "${final_pr_number}" != "${PR_NUMBER}" ]]', final_step)
        self.assertIn("Selected tap pull request changed before final verification.", final_step)
        self.assertEqual(2, final_step.count("\n          verify_remote_branch\n"))
        self.assertIn('gh pr view "${PR_NUMBER}"', final_step)
        self.assertLess(
            text.index("Open or reuse tap pull request"),
            text.index("Reverify tap branch and pull request identity"),
        )

    def test_publisher_runs_homebrew_only_after_sign_and_publish(self) -> None:
        text = self.publisher_text()
        self.assertIn("  homebrew:", text)
        self.assertIn("needs: [validate, sign-and-publish]", text)
        self.assertIn("uses: ./.github/workflows/reusable-homebrew-update.yml", text)
        self.assertIn("source_tag: ${{ needs.validate.outputs.source_tag }}", text)
        self.assertIn("tap_token: ${{ secrets.HOMEBREW_TAP_TOKEN }}", text)

    def test_tag_selected_build_and_apple_release_never_receive_homebrew_token(self) -> None:
        build = BUILD_EXAMPLE.read_text(encoding="utf-8")
        privileged_release = REUSABLE_RELEASE.read_text(encoding="utf-8")
        publisher = self.publisher_text()

        for label, text in (
            ("tag-selected release build", build),
            ("Apple signing reusable release", privileged_release),
        ):
            with self.subTest(label=label):
                self.assertNotIn("HOMEBREW_TAP_TOKEN", text)
                self.assertNotIn("secrets.tap_token", text)

        self.assertEqual(1, publisher.count("HOMEBREW_TAP_TOKEN"))
        homebrew_start = publisher.index("  homebrew:")
        self.assertGreater(publisher.index("HOMEBREW_TAP_TOKEN"), homebrew_start)

    def test_homebrew_write_path_is_after_immutable_publication_path(self) -> None:
        publisher = self.publisher_text()
        homebrew = publisher.index("  homebrew:")
        sign_and_publish = publisher.index("  sign-and-publish:")
        self.assertLess(sign_and_publish, homebrew)
        self.assertIn("needs: [validate, sign-and-publish]", publisher[homebrew:])
        self.assertIn("publish_github_release: true", publisher[sign_and_publish:homebrew])


if __name__ == "__main__":
    unittest.main()
