from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
QUALITY_WORKFLOW = REPO_ROOT / ".github/workflows/quality.yml"


class QualityReleaseIsolationContractTests(unittest.TestCase):
    def quality_text(self) -> str:
        return QUALITY_WORKFLOW.read_text(encoding="utf-8")

    def test_repository_hygiene_runs_release_isolation_contract(self) -> None:
        text = self.quality_text()
        self.assertIn("- name: Release isolation contract", text)
        for module in (
            "scripts.release.test_release_provenance",
            "scripts.release.test_validate_actions_artifact",
            "scripts.release.test_validate_release_input",
            "scripts.release.test_release_workflow_contract",
            "scripts.release.test_release_publisher_workflow_contract",
            "scripts.release.test_privileged_release_workflow_contract",
            "scripts.release.test_homebrew_publisher_workflow_contract",
            "scripts.release.test_verify_validated_release_metadata",
        ):
            with self.subTest(module=module):
                self.assertIn(module, text)
        self.assertIn("scripts/release/test-resolve-release-build-artifact.sh", text)
        self.assertIn("scripts/release/test-verify-release-source.sh", text)

    def test_required_gate_depends_on_repository_hygiene(self) -> None:
        text = self.quality_text()
        self.assertIn("      - repository-hygiene", text)
        self.assertIn("REPOSITORY_HYGIENE: ${{ needs.repository-hygiene.result }}", text)
        self.assertIn('[[ "${REPOSITORY_HYGIENE}" == success ]]', text)


if __name__ == "__main__":
    unittest.main()
