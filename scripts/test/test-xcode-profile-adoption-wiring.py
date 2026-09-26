from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/test-profile-adoption.yml"
INFRASTRUCTURE = ROOT / ".github/workflows/test-infrastructure.yml"
ACTIONLINT = ROOT / ".github/actionlint.yaml"


class XcodeProfileAdoptionWiringTests(unittest.TestCase):
    def test_macos_app_profile_uses_production_xcode_runtime_paths(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for token in (
            '"profile": "macos-app"',
            '"adapter": "xcode"',
            "prepare-macos-app:",
            "macos-app-unit:",
            "macos-app-e2e:",
            "Verify macos-app profile adoption",
            "Tests/AdoptionFixtures/Xcode",
            "project_path: AdoptionApp.xcodeproj",
            "scheme: AdoptionApp",
            "reusable-swift-tests.yml",
            "reusable-macos-e2e.yml",
            "bootstrap_coverage: true",
        ):
            with self.subTest(token=token):
                self.assertIn(token, workflow)

    def test_macos_app_verifier_requires_coverage_and_e2e_but_not_visual(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for assertion in (
            '[[ "${COVERAGE_ENABLED}" == true ]]',
            '[[ "${COVERAGE_REQUIRED}" == true ]]',
            '[[ "${E2E_ENABLED}" == true ]]',
            '[[ "${E2E_REQUIRED}" == true ]]',
            '[[ "${VISUAL_ENABLED}" == false ]]',
            '[[ "${VISUAL_REQUIRED}" == false ]]',
            '[[ "${COVERAGE_RESULT}" == success ]]',
            '[[ "${E2E_RESULT}" == success ]]',
        ):
            with self.subTest(assertion=assertion):
                self.assertIn(assertion, workflow)

    def test_macos_ui_strict_profile_runs_required_visual_comparison(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for token in (
            '"profile": "macos-ui-strict"',
            "prepare-macos-ui-strict:",
            "macos-ui-strict-visual:",
            "Verify macos-ui-strict profile adoption",
            "reusable-visual-regression.yml",
            "Tests/AdoptionFixtures/Xcode/VisualRegression/visual-regression.json",
            "adoption-macos-ui-strict-baseline",
            "bootstrap_rolling: ${{ needs.prepare-macos-ui-strict.outputs.visual_bootstrap == 'true' }}",
        ):
            with self.subTest(token=token):
                self.assertIn(token, workflow)

        for assertion in (
            '[[ "${COVERAGE_ENABLED}" == true ]]',
            '[[ "${COVERAGE_REQUIRED}" == true ]]',
            '[[ "${E2E_ENABLED}" == true ]]',
            '[[ "${E2E_REQUIRED}" == true ]]',
            '[[ "${VISUAL_ENABLED}" == true ]]',
            '[[ "${VISUAL_REQUIRED}" == true ]]',
            '[[ "${VISUAL_BOOTSTRAP}" == false ]]',
            '[[ "${VISUAL_RESULT}" == success ]]',
        ):
            with self.subTest(assertion=assertion):
                self.assertIn(assertion, workflow)

    def test_adoption_workflow_remains_read_only_and_secret_free(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("secrets: inherit", workflow)
        self.assertNotIn("environment: release", workflow)

    def test_actionlint_ignores_for_self_reusable_calls_are_path_scoped(self) -> None:
        config = ACTIONLINT.read_text(encoding="utf-8")
        self.assertIn(".github/workflows/test-profile-adoption.yml:", config)
        for reusable in (
            "reusable-macos-e2e",
            "reusable-visual-regression",
        ):
            with self.subTest(reusable=reusable):
                self.assertIn(
                    f'reusable workflow call "\\\\$/\\\\.github/workflows/{reusable}\\\\.yml"',
                    config,
                )

    def test_test_infrastructure_runs_xcode_adoption_contract(self) -> None:
        workflow = INFRASTRUCTURE.read_text(encoding="utf-8")
        self.assertIn("scripts/test/test-xcode-profile-adoption-wiring.py", workflow)


if __name__ == "__main__":
    unittest.main()
