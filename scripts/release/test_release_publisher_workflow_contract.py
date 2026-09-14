from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISHER_WORKFLOW = REPO_ROOT / "examples/app-release-publisher.yml"


def job_block(text: str, job_name: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line == f"  {job_name}:":
            start = index
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.fullmatch(r"  [A-Za-z0-9_-]+:", lines[index]):
            end = index
            break
    return "\n".join(lines[start:end]) + "\n"


class ReleasePublisherWorkflowContractTests(unittest.TestCase):
    def workflow_text(self) -> str:
        self.assertTrue(
            PUBLISHER_WORKFLOW.is_file(),
            f"missing publisher workflow example: {PUBLISHER_WORKFLOW}",
        )
        return PUBLISHER_WORKFLOW.read_text(encoding="utf-8")

    def test_uses_workflow_run_for_release_build(self) -> None:
        text = self.workflow_text()
        self.assertIn("name: Release Publisher", text)
        self.assertRegex(text, r"(?ms)^on:\n  workflow_run:\n    workflows:\n      - \"Release Build\"\n    types:\n      - completed$")

    def test_workflow_permissions_default_to_none(self) -> None:
        self.assertRegex(self.workflow_text(), r"(?m)^permissions: \{\}$")

    def test_validation_job_is_secret_free_and_read_only(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertTrue(block, "validate job is required")
        self.assertRegex(block, r"(?m)^    permissions:\n      actions: read\n      contents: read$")
        self.assertNotIn("environment:", block)
        self.assertNotIn("contents: write", block)
        for token in (
            "MACOS_CERTIFICATE_P12_BASE64",
            "MACOS_CERTIFICATE_PASSWORD",
            "APP_STORE_CONNECT_API_KEY_P8",
            "APP_STORE_CONNECT_KEY_ID",
            "APP_STORE_CONNECT_ISSUER_ID",
            "HOMEBREW_TAP_TOKEN",
            "secrets.",
        ):
            with self.subTest(token=token):
                self.assertNotIn(token, block)

    def test_validation_only_accepts_successful_upstream_run(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertIn("github.event.workflow_run.conclusion == 'success'", block)

    def test_checkout_is_bound_to_publisher_sha_with_full_history(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertIn("ref: ${{ github.sha }}", block)
        self.assertIn("fetch-depth: 0", block)
        self.assertIn("persist-credentials: false", block)

    def test_resolves_exact_triggering_run_and_attempt(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertIn("scripts/release/resolve-release-build-artifact.sh", block)
        self.assertIn("SOURCE_RUN_ID: ${{ github.event.workflow_run.id }}", block)
        self.assertIn("SOURCE_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}", block)
        self.assertIn('--run-id "${SOURCE_RUN_ID}"', block)
        self.assertIn('--run-attempt "${SOURCE_RUN_ATTEMPT}"', block)
        self.assertIn("--workflow-path .github/workflows/release-build.yml", block)

    def test_independently_verifies_tag_binding_and_release_input(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertIn("scripts/release/verify-release-source.sh", block)
        self.assertIn("scripts/release/validate-release-input.py", block)
        self.assertIn("--publisher-sha \"${GITHUB_SHA}\"", block)
        self.assertIn("--source-is-ancestor true", block)

    def test_reuploads_validated_input_inside_publisher_run(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertIn(
            "validated-release-input-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.event.workflow_run.id }}-${{ github.event.workflow_run.run_attempt }}",
            block,
        )
        self.assertRegex(
            block,
            re.compile(
                r"path: \|\n"
                r"\s+validated-release-input/unsigned-macos-app\.tar\.gz\n"
                r"\s+validated-release-input/validated-release-metadata\.json",
                re.MULTILINE,
            ),
        )

    def test_exports_exact_validated_artifact_identity(self) -> None:
        block = job_block(self.workflow_text(), "validate")
        self.assertIn("id: validated_upload", block)
        self.assertIn(
            "validated_artifact_id: ${{ steps.validated_upload.outputs.artifact-id }}",
            block,
        )
        self.assertIn(
            "validated_artifact_digest: ${{ steps.validated_upload.outputs.artifact-digest }}",
            block,
        )

        privileged = job_block(self.workflow_text(), "sign-and-publish")
        self.assertIn(
            "validated_artifact_id: ${{ needs.validate.outputs.validated_artifact_id }}",
            privileged,
        )
        self.assertIn(
            "validated_artifact_digest: ${{ needs.validate.outputs.validated_artifact_digest }}",
            privileged,
        )

    def test_concurrency_is_per_source_run_and_never_cancels_in_progress_release(self) -> None:
        text = self.workflow_text()
        self.assertIn(
            "group: release-publisher-${{ github.event.workflow_run.id }}-${{ github.event.workflow_run.run_attempt }}",
            text,
        )
        self.assertIn("cancel-in-progress: false", text)


if __name__ == "__main__":
    unittest.main()
