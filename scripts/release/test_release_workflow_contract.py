from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_WORKFLOW = REPO_ROOT / "examples/app-release-build.yml"
LEGACY_WORKFLOW = REPO_ROOT / "examples/app-release.yml"


class ReleaseBuildWorkflowContractTests(unittest.TestCase):
    def workflow_text(self) -> str:
        self.assertTrue(BUILD_WORKFLOW.is_file(), f"missing workflow example: {BUILD_WORKFLOW}")
        return BUILD_WORKFLOW.read_text(encoding="utf-8")

    def test_workflow_is_tag_triggered_release_build(self) -> None:
        text = self.workflow_text()
        self.assertIn("name: Release Build", text)
        self.assertIn('      - "v[0-9]+.[0-9]+.[0-9]+"', text)

    def test_workflow_level_permissions_are_empty(self) -> None:
        text = self.workflow_text()
        self.assertRegex(text, r"(?m)^permissions: \{\}$")

    def test_build_job_has_read_only_contents(self) -> None:
        text = self.workflow_text()
        self.assertRegex(
            text,
            r"(?ms)^jobs:\n  build:.*?^    permissions:\n      contents: read$",
        )
        self.assertNotIn("contents: write", text)

    def test_build_workflow_has_no_release_environment_or_privileged_secret_names(self) -> None:
        text = self.workflow_text()
        forbidden = (
            "environment:",
            "MACOS_CERTIFICATE_P12_BASE64",
            "MACOS_CERTIFICATE_PASSWORD",
            "APP_STORE_CONNECT_API_KEY_P8",
            "APP_STORE_CONNECT_KEY_ID",
            "APP_STORE_CONNECT_ISSUER_ID",
            "HOMEBREW_TAP_TOKEN",
            "tap_token",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, text)

    def test_artifact_name_is_bound_to_run_id_and_attempt(self) -> None:
        text = self.workflow_text()
        self.assertIn(
            "unsigned-macos-release-${{ github.run_id }}-${{ github.run_attempt }}",
            text,
        )

    def test_build_writes_and_uploads_provenance_with_archive(self) -> None:
        text = self.workflow_text()
        self.assertIn("scripts/release/write-build-provenance.py", text)
        self.assertIn("artifact-payload/release-input/unsigned-macos-app.tar.gz", text)
        self.assertIn("artifact-payload/release-input/build-provenance.json", text)
        self.assertRegex(
            text,
            re.compile(
                r"path: artifact-payload/\n",
                re.MULTILINE,
            ),
        )
        self.assertNotRegex(
            text,
            re.compile(
                r"path: \|\n"
                r"\s+release-input/unsigned-macos-app\.tar\.gz\n"
                r"\s+release-input/build-provenance\.json",
                re.MULTILINE,
            ),
        )

    def test_build_does_not_call_privileged_release_or_homebrew_reusable_workflow(self) -> None:
        text = self.workflow_text()
        self.assertNotIn("reusable-macos-release.yml", text)
        self.assertNotIn("reusable-homebrew-update.yml", text)

    def test_legacy_monolithic_example_is_migration_only(self) -> None:
        text = LEGACY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("MIGRATION ONLY", text)
        self.assertIn("app-release-build.yml", text)
        self.assertIn("app-release-publisher.yml", text)
        self.assertNotIn("uses: ./.github/workflows/reusable-macos-release.yml", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("environment: release", text)


if __name__ == "__main__":
    unittest.main()
