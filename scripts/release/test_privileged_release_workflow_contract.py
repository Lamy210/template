from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
REUSABLE_RELEASE = REPO_ROOT / ".github/workflows/reusable-macos-release.yml"
PUBLISHER_EXAMPLE = REPO_ROOT / "examples/app-release-publisher.yml"
RELEASE_DOC = REPO_ROOT / "docs/RELEASE.md"
SETUP_DOC = REPO_ROOT / "docs/SETUP.md"


def job_block(text: str, job_id: str) -> str:
    marker = f"  {job_id}:\n"
    start = text.find(marker)
    if start < 0:
        return ""
    next_job = text.find("\n  ", start + len(marker))
    return text[start:] if next_job < 0 else text[start:next_job]


class PrivilegedReleaseWorkflowContractTests(unittest.TestCase):
    def release_text(self) -> str:
        return REUSABLE_RELEASE.read_text(encoding="utf-8")

    def publisher_text(self) -> str:
        return PUBLISHER_EXAMPLE.read_text(encoding="utf-8")

    def test_privileged_workflow_requires_validated_source_inputs(self) -> None:
        text = self.release_text()
        for input_name in (
            "validated_artifact_name:",
            "validated_artifact_id:",
            "validated_artifact_digest:",
            "source_tag:",
            "source_sha:",
            "source_version:",
            "source_run_id:",
            "source_run_attempt:",
            "source_artifact_id:",
            "source_artifact_digest:",
            "archive_sha256:",
        ):
            with self.subTest(input_name=input_name):
                self.assertIn(input_name, text)

    def test_privileged_workflow_never_derives_release_identity_from_github_ref(self) -> None:
        text = self.release_text()
        for forbidden in (
            "github.ref_name",
            "GITHUB_REF_NAME",
            "GITHUB_REF_TYPE",
            "release_branch:",
            "inputs.release_branch",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_privileged_checkout_is_publisher_sha_not_release_tag(self) -> None:
        text = self.release_text()
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("Checkout tagged release source", text)

    def test_downloads_exact_validated_artifact_id(self) -> None:
        text = self.release_text()
        self.assertIn("actions: read", text)
        self.assertIn("artifact-ids: ${{ inputs.validated_artifact_id }}", text)
        self.assertNotIn("name: ${{ inputs.validated_artifact_name }}", text)
        self.assertIn("VALIDATED_ARTIFACT_DIGEST: ${{ inputs.validated_artifact_digest }}", text)

    def test_validated_artifact_identity_uses_trusted_verifier_before_download(self) -> None:
        text = self.release_text()
        self.assertIn("scripts/release/verify-validated-artifact.py", text)
        verifier = text.index("scripts/release/verify-validated-artifact.py")
        download = text.index("actions/download-artifact")
        self.assertLess(verifier, download)
        for token in (
            "VALIDATED_ARTIFACT_ID: ${{ inputs.validated_artifact_id }}",
            "VALIDATED_ARTIFACT_NAME: ${{ inputs.validated_artifact_name }}",
            "VALIDATED_ARTIFACT_DIGEST: ${{ inputs.validated_artifact_digest }}",
            "SOURCE_RUN_ID: ${{ inputs.source_run_id }}",
            "SOURCE_RUN_ATTEMPT: ${{ inputs.source_run_attempt }}",
            "PUBLISHER_RUN_ID: ${{ github.run_id }}",
            "PUBLISHER_RUN_ATTEMPT: ${{ github.run_attempt }}",
            "PUBLISHER_SHA: ${{ github.sha }}",
            "REPOSITORY_ID: ${{ github.repository_id }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
        self.assertIn('--publisher-sha "${PUBLISHER_SHA}"', text)
        self.assertIn('--repository-id "${REPOSITORY_ID}"', text)

    def test_validated_metadata_and_archive_are_reverified_before_certificate_import(self) -> None:
        text = self.release_text()
        verifier = text.index("scripts/release/verify-validated-release-metadata.py")
        extractor = text.index("scripts/release/extract-app-artifact.sh")
        certificate = text.index("scripts/release/import-certificate.sh")
        self.assertLess(verifier, certificate)
        self.assertLess(extractor, certificate)
        self.assertIn("inputs.archive_sha256", text)
        self.assertIn("SOURCE_ARTIFACT_ID: ${{ inputs.source_artifact_id }}", text)
        self.assertIn("SOURCE_ARTIFACT_DIGEST: ${{ inputs.source_artifact_digest }}", text)
        self.assertIn('--source-artifact-id "${SOURCE_ARTIFACT_ID}"', text)
        self.assertIn('--source-artifact-digest "${SOURCE_ARTIFACT_DIGEST}"', text)

    def test_privileged_revalidation_rejects_symlinked_info_plist_before_secrets(self) -> None:
        text = self.release_text()
        revalidation = text.index("- name: Revalidate application metadata before secrets")
        certificate = text.index("scripts/release/import-certificate.sh")
        self.assertLess(revalidation, certificate)
        self.assertIn('if [[ ! -f "${plist}" || -L "${plist}" ]]; then', text)
        plist_guard = text.index('if [[ ! -f "${plist}" || -L "${plist}" ]]; then')
        plist_read = text.index("PlistBuddy -c 'Print :CFBundleIdentifier'")
        self.assertLess(plist_guard, plist_read)

    def test_dmg_name_is_validated_before_certificate_import(self) -> None:
        text = self.release_text()
        validation = text.index("- name: Validate trusted release output name before secrets")
        certificate = text.index("scripts/release/import-certificate.sh")
        self.assertLess(validation, certificate)
        self.assertIn("scripts/release/validate-release-output-name.py", text)
        self.assertIn("DMG_NAME: ${{ inputs.dmg_name }}", text)
        self.assertIn('--dmg-name "${DMG_NAME}"', text)

    def test_validated_metadata_is_rebound_to_current_publisher_attempt(self) -> None:
        text = self.release_text()
        self.assertIn('--publisher-run-id "${GITHUB_RUN_ID}"', text)
        self.assertIn('--publisher-run-attempt "${GITHUB_RUN_ATTEMPT}"', text)

    def test_tag_binding_is_rechecked_before_secrets_and_publication(self) -> None:
        text = self.release_text()
        before_secrets = text.index("- name: Rebind release tag before secrets")
        certificate = text.index("scripts/release/import-certificate.sh")
        before_publication = text.index("- name: Rebind release tag before publication")
        publication = text.index("scripts/release/publish-github-release.sh")

        self.assertLess(before_secrets, certificate)
        self.assertLess(certificate, before_publication)
        self.assertLess(before_publication, publication)
        self.assertGreaterEqual(text.count("scripts/release/verify-release-source.sh"), 2)
        self.assertGreaterEqual(text.count("SOURCE_TAG: ${{ inputs.source_tag }}"), 2)
        self.assertGreaterEqual(text.count("SOURCE_SHA: ${{ inputs.source_sha }}"), 2)
        self.assertGreaterEqual(text.count("PUBLISHER_SHA: ${{ github.sha }}"), 2)

    def test_verified_release_artifact_is_bound_to_publisher_attempt(self) -> None:
        text = self.release_text()
        self.assertIn(
            "name: verified-macos-release-${{ github.run_id }}-${{ github.run_attempt }}",
            text,
        )
        self.assertNotIn("name: verified-macos-release\n", text)

    def test_final_release_attestation_is_generated_before_upload_and_publication(self) -> None:
        text = self.release_text()
        writer = text.index("- name: Write final release attestation")
        upload = text.index("- name: Upload verified release artifacts")
        publication = text.index("- name: Publish immutable GitHub Release")
        self.assertLess(writer, upload)
        self.assertLess(writer, publication)
        self.assertIn("scripts/release/write-release-provenance.py", text)
        for token in (
            "SOURCE_RUN_ID: ${{ inputs.source_run_id }}",
            "SOURCE_RUN_ATTEMPT: ${{ inputs.source_run_attempt }}",
            "SOURCE_ARTIFACT_ID: ${{ inputs.source_artifact_id }}",
            "SOURCE_ARTIFACT_DIGEST: ${{ inputs.source_artifact_digest }}",
            "ARCHIVE_SHA256: ${{ inputs.archive_sha256 }}",
            "PUBLISHER_RUN_ID: ${{ github.run_id }}",
            "PUBLISHER_SHA: ${{ github.sha }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
        self.assertGreaterEqual(text.count("release-output/release-provenance.json"), 2)
        self.assertIn(
            "RELEASE_PROVENANCE_PATH: release-output/release-provenance.json",
            text,
        )

    def test_github_release_uses_validated_source_tag(self) -> None:
        text = self.release_text()
        self.assertIn("TAG_NAME: ${{ inputs.source_tag }}", text)

    def test_only_privileged_reusable_release_job_uses_release_environment(self) -> None:
        text = self.release_text()
        self.assertEqual(1, text.count("environment: release"))
        self.assertIn("contents: write", text)

    def test_signing_job_has_apple_secrets_but_no_repository_write_token(self) -> None:
        block = job_block(self.release_text(), "release")
        self.assertTrue(block, "release signing job is required")
        self.assertIn("environment: release", block)
        self.assertIn("actions: read", block)
        self.assertIn("contents: read", block)
        self.assertNotIn("contents: write", block)
        for token in (
            "MACOS_CERTIFICATE_P12_BASE64",
            "MACOS_CERTIFICATE_PASSWORD",
            "APP_STORE_CONNECT_API_KEY_P8",
            "APP_STORE_CONNECT_KEY_ID",
            "APP_STORE_CONNECT_ISSUER_ID",
        ):
            with self.subTest(token=token):
                self.assertIn(token, block)
        self.assertNotIn("Publish immutable GitHub Release", block)

    def test_publication_job_is_separate_write_boundary_without_apple_secrets(self) -> None:
        block = job_block(self.release_text(), "publish")
        self.assertTrue(block, "separate publish job is required")
        self.assertIn("needs: release", block)
        self.assertIn("actions: read", block)
        self.assertIn("contents: write", block)
        self.assertNotIn("environment: release", block)
        for token in (
            "MACOS_CERTIFICATE_P12_BASE64",
            "MACOS_CERTIFICATE_PASSWORD",
            "APP_STORE_CONNECT_API_KEY_P8",
            "APP_STORE_CONNECT_KEY_ID",
            "APP_STORE_CONNECT_ISSUER_ID",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, block)
        self.assertIn("scripts/release/verify-verified-release-artifact.py", block)
        self.assertIn("artifact-ids: ${{ needs.release.outputs.verified_artifact_id }}", block)
        self.assertIn("Rebind release tag before publication", block)
        self.assertIn("Publish immutable GitHub Release", block)

    def test_verified_release_handoff_exports_exact_artifact_identity(self) -> None:
        block = job_block(self.release_text(), "release")
        self.assertIn("id: verified_upload", block)
        self.assertIn("id: verified_identity", block)
        self.assertIn("scripts/release/normalize-artifact-identity.py", block)
        self.assertIn(
            "verified_artifact_id: ${{ steps.verified_identity.outputs.id }}",
            block,
        )
        self.assertIn(
            "verified_artifact_digest: ${{ steps.verified_identity.outputs.digest }}",
            block,
        )
        self.assertIn(
            "verified_artifact_name: verified-macos-release-${{ github.run_id }}-${{ github.run_attempt }}",
            block,
        )

    def test_publisher_privileged_job_depends_on_validation_and_calls_trusted_reusable(self) -> None:
        text = self.publisher_text()
        self.assertIn("  sign-and-publish:", text)
        self.assertIn("needs: validate", text)
        self.assertIn("uses: ./.github/workflows/reusable-macos-release.yml", text)
        self.assertIn("validated_artifact_name: ${{ needs.validate.outputs.validated_artifact_name }}", text)
        self.assertIn("validated_artifact_id: ${{ needs.validate.outputs.validated_artifact_id }}", text)
        self.assertIn(
            "validated_artifact_digest: ${{ needs.validate.outputs.validated_artifact_digest }}",
            text,
        )
        self.assertIn("source_tag: ${{ needs.validate.outputs.source_tag }}", text)
        self.assertIn("source_sha: ${{ needs.validate.outputs.source_sha }}", text)
        self.assertIn("source_version: ${{ needs.validate.outputs.source_version }}", text)
        self.assertIn("source_artifact_id: ${{ needs.validate.outputs.source_artifact_id }}", text)
        self.assertIn(
            "source_artifact_digest: ${{ needs.validate.outputs.source_artifact_digest }}",
            text,
        )
        self.assertIn("archive_sha256: ${{ needs.validate.outputs.archive_sha256 }}", text)

    def test_publisher_does_not_inherit_repository_or_organization_secrets(self) -> None:
        text = self.publisher_text()
        self.assertNotIn("secrets: inherit", text)

    def test_rollout_docs_require_immutable_release_tag_ruleset(self) -> None:
        text = RELEASE_DOC.read_text(encoding="utf-8")
        self.assertIn("refs/tags/v*", text)
        self.assertIn("allow initial creation", text)
        self.assertIn("reject update", text)
        self.assertIn("reject deletion", text)
        self.assertIn("Do not enable", text)

    def test_setup_requires_release_environment_default_branch_restriction(self) -> None:
        text = SETUP_DOC.read_text(encoding="utf-8")
        self.assertIn("Selected branches and tags", text)
        self.assertIn("default branch", text)
        self.assertIn("Do not leave the `release` Environment unrestricted", text)
        self.assertNotIn("Where supported and useful, configure environment protection", text)

    def test_pre_split_ancestor_fails_safely_without_privileged_fallback(self) -> None:
        text = RELEASE_DOC.read_text(encoding="utf-8")
        self.assertIn("predates `.github/workflows/release-build.yml`", text)
        self.assertIn("safe failure", text)
        self.assertIn("Do not add a fallback", text)

    def test_retry_docs_require_full_publisher_rerun(self) -> None:
        text = RELEASE_DOC.read_text(encoding="utf-8")
        retry = text.split("### Publisher/signing retry", 1)[1].split(
            "### Expired source artifact", 1
        )[0]
        self.assertIn("Re-run all jobs", retry)
        self.assertIn("Do not use `Re-run failed jobs`", retry)
        self.assertIn("current `github.run_attempt`", retry)
    def test_rollout_requires_post_split_ancestor_runtime_verification(self) -> None:
        text = RELEASE_DOC.read_text(encoding="utf-8")
        migration = text.split("## Migration checklist", 1)[1].split("## Rollback", 1)[0]
        self.assertIn("post-split ancestor", migration)
        self.assertIn("current default-branch publisher", migration)
        self.assertIn("disposable repository", migration)
        self.assertIn("before enabling", migration)


if __name__ == "__main__":
    unittest.main()
