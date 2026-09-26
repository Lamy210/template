from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/test-profile-adoption.yml"
INFRASTRUCTURE = ROOT / ".github/workflows/test-infrastructure.yml"


class SwiftPMProfileAdoptionWiringTests(unittest.TestCase):
    def test_workflow_is_read_only_and_secret_free(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertNotIn("secrets: inherit", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("environment: release", workflow)
        for secret_name in (
            "MACOS_CERTIFICATE_P12_BASE64",
            "MACOS_CERTIFICATE_PASSWORD",
            "APP_STORE_CONNECT_API_KEY_P8",
            "HOMEBREW_TAP_TOKEN",
        ):
            with self.subTest(secret_name=secret_name):
                self.assertNotIn(secret_name, workflow)

    def test_workflow_uses_production_profile_and_test_paths(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for token in (
            '"profile": "minimal"',
            '"profile": "standard"',
            "resolve-test-profile.py",
            "classify-test-policy.py",
            "emit-profile-adoption-outputs.py",
            "reusable-swift-tests.yml",
            "Tests/AdoptionFixtures/SwiftPM",
            "bootstrap_coverage: true",
            "Verify SwiftPM profile adoption",
        ):
            with self.subTest(token=token):
                self.assertIn(token, workflow)

    def test_runtime_profiles_are_not_hardcoded_around_resolver_outputs(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "enable_coverage: ${{ needs.prepare-standard.outputs.coverage_enabled == 'true' }}",
            workflow,
        )
        self.assertIn(
            "coverage_required: ${{ needs.prepare-standard.outputs.coverage_required == 'true' }}",
            workflow,
        )

    def test_test_infrastructure_covers_adoption_contract(self) -> None:
        workflow = INFRASTRUCTURE.read_text(encoding="utf-8")
        self.assertEqual(2, workflow.count('"Tests/AdoptionFixtures/**"'))
        self.assertEqual(
            2,
            workflow.count('".github/workflows/test-profile-adoption.yml"'),
        )
        for test_path in (
            "scripts/test/test-adoption-fixture-contract.py",
            "scripts/test/test-emit-profile-adoption-outputs.py",
            "scripts/test/test-swiftpm-profile-adoption-wiring.py",
        ):
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, workflow)


if __name__ == "__main__":
    unittest.main()
