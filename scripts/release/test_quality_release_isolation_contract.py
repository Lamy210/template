from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALITY_WORKFLOW = REPO_ROOT / ".github/workflows/quality.yml"
RELEASE_ISOLATION_WORKFLOW = REPO_ROOT / ".github/workflows/release-isolation-tdd.yml"


class QualityReleaseIsolationContractTests(unittest.TestCase):
    def quality_text(self) -> str:
        return QUALITY_WORKFLOW.read_text(encoding="utf-8")

    def test_repository_hygiene_runs_release_isolation_contract(self) -> None:
        text = self.quality_text()
        self.assertIn("- name: Release isolation contract", text)
        for module in (
            "scripts.release.test_release_provenance",
            "scripts.release.test_release_attestation",
            "scripts.release.test_validate_actions_artifact",
            "scripts.release.test_validate_release_input",
            "scripts.release.test_publisher_attempt_binding",
            "scripts.release.test_validated_artifact",
            "scripts.release.test_verified_release_archive",
            "scripts.release.test_release_environment_runtime_proof",
            "scripts.release.test_release_workflow_contract",
            "scripts.release.test_release_publisher_workflow_contract",
            "scripts.release.test_privileged_release_workflow_contract",
            "scripts.release.test_homebrew_publisher_workflow_contract",
            "scripts.release.test_release_download_identity",
            "scripts.homebrew.test_tap_repository_identity",
            "scripts.release.test_unprivileged_release_build_workflow",
            "scripts.release.test_verify_validated_release_metadata",
        ):
            with self.subTest(module=module):
                self.assertIn(module, text)
        self.assertIn("scripts/release/test-resolve-release-build-artifact.sh", text)
        self.assertIn("scripts/release/test-verify-release-source.sh", text)
        self.assertIn("scripts/release/test-download-exact-release-assets.sh", text)

    def test_dedicated_release_isolation_runs_tap_repository_identity_contract(self) -> None:
        text = RELEASE_ISOLATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts.homebrew.test_tap_repository_identity", text)
        self.assertIn("scripts.release.test_release_download_identity", text)
        self.assertIn("scripts/release/test-download-exact-release-assets.sh", text)

    def test_release_isolation_roundtrip_binds_verified_artifact_raw_zip(self) -> None:
        text = RELEASE_ISOLATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "/actions/artifacts/${ARTIFACT_ID}/zip",
            text,
        )
        self.assertIn(
            "scripts/release/extract-verified-release-artifact.py",
            text,
        )
        self.assertIn(
            "ARTIFACT_DIGEST: ${{ needs.verified-release-package.outputs.artifact_digest }}",
            text,
        )
        self.assertIn('--expected-digest "${ARTIFACT_DIGEST}"', text)

    def test_release_isolation_runs_on_pull_requests_and_post_merge_main(self) -> None:
        text = RELEASE_ISOLATION_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  pull_request:\n", text)
        self.assertIn("  push:\n    branches:\n      - main\n", text)
        self.assertIn("  workflow_dispatch:\n", text)
        self.assertIn(
            "group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}",
            text,
        )
        self.assertIn(
            "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
            text,
        )

    def test_quality_permission_fixture_is_scoped_to_run_attempt(self) -> None:
        text = self.quality_text()
        artifact_name = "release-app-permission-fixture-${{ github.run_attempt }}"
        self.assertGreaterEqual(text.count(artifact_name), 2)
        self.assertNotIn("name: release-app-permission-fixture\n", text)

    def test_quality_permission_fixture_uses_exact_artifact_identity(self) -> None:
        text = self.quality_text()

        for token in (
            "id: fixture_upload",
            "artifact_id: ${{ steps.fixture_upload.outputs.artifact-id }}",
            "artifact_digest: ${{ steps.fixture_upload.outputs.artifact-digest }}",
            "actions: read",
            "Validate exact packaged app fixture identity",
            "scripts/ci/current_run_artifact_identity.py",
            "artifact-ids: ${{ needs.release-artifact-package.outputs.artifact_id }}",
            "merge-multiple: true",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

        download = text.index("- name: Download packaged app fixture")
        extract = text.index("- name: Extract and verify executable permission")
        self.assertLess(download, extract)
        download_block = text[download:extract]
        self.assertNotIn("name: release-app-permission-fixture", download_block)

    def test_required_gate_depends_on_repository_hygiene(self) -> None:
        text = self.quality_text()
        self.assertIn("      - repository-hygiene", text)
        self.assertIn("REPOSITORY_HYGIENE: ${{ needs.repository-hygiene.result }}", text)
        self.assertIn('[[ "${REPOSITORY_HYGIENE}" == success ]]', text)


if __name__ == "__main__":
    unittest.main()
