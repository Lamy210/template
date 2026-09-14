from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
REUSABLE_RELEASE = REPO_ROOT / ".github/workflows/reusable-macos-release.yml"
PUBLISHER_EXAMPLE = REPO_ROOT / "examples/app-release-publisher.yml"


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

    def test_validated_metadata_and_archive_are_reverified_before_certificate_import(self) -> None:
        text = self.release_text()
        verifier = text.index("scripts/release/verify-validated-release-metadata.py")
        extractor = text.index("scripts/release/extract-app-artifact.sh")
        certificate = text.index("scripts/release/import-certificate.sh")
        self.assertLess(verifier, certificate)
        self.assertLess(extractor, certificate)
        self.assertIn("inputs.archive_sha256", text)

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

    def test_github_release_uses_validated_source_tag(self) -> None:
        text = self.release_text()
        self.assertIn("TAG_NAME: ${{ inputs.source_tag }}", text)

    def test_only_privileged_reusable_release_job_uses_release_environment(self) -> None:
        text = self.release_text()
        self.assertEqual(1, text.count("environment: release"))
        self.assertIn("contents: write", text)

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
        self.assertIn("archive_sha256: ${{ needs.validate.outputs.archive_sha256 }}", text)

    def test_publisher_does_not_inherit_repository_or_organization_secrets(self) -> None:
        text = self.publisher_text()
        self.assertNotIn("secrets: inherit", text)


if __name__ == "__main__":
    unittest.main()
