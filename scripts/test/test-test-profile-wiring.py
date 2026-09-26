from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/tests.yml"
INFRASTRUCTURE = ROOT / ".github/workflows/test-infrastructure.yml"


class TestProfileWiringTests(unittest.TestCase):
    def test_tests_workflow_resolves_profile_before_classification(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            "MACOS_TEST_PROFILE: ${{ vars.MACOS_TEST_PROFILE }}",
            workflow,
        )
        self.assertIn("python3 scripts/test/resolve-test-profile.py", workflow)
        self.assertIn("--from-env", workflow)
        self.assertIn('--output "${RUNNER_TEMP}/test-policy.json"', workflow)
        self.assertIn("python3 scripts/test/classify-test-policy.py", workflow)
        self.assertIn('--input "${RUNNER_TEMP}/test-policy.json"', workflow)

        classifier_block = workflow.split(
            "python3 scripts/test/classify-test-policy.py",
            maxsplit=1,
        )[1].split("--github-output", maxsplit=1)[0]
        self.assertNotIn("--from-env", classifier_block)

    def test_downstream_topology_and_stable_names_are_preserved(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for stable_name in (
            "Unit runner",
            "Integration runner",
            "E2E runner",
            "Visual runner",
            "Coverage",
            "Tests / Required Gate",
        ):
            with self.subTest(stable_name=stable_name):
                self.assertIn(stable_name, workflow)

        for reusable in (
            "reusable-swift-tests.yml",
            "reusable-macos-e2e.yml",
            "reusable-visual-regression.yml",
        ):
            with self.subTest(reusable=reusable):
                self.assertIn(reusable, workflow)

    def test_test_infrastructure_covers_profile_wiring_changes(self) -> None:
        workflow = INFRASTRUCTURE.read_text(encoding="utf-8")
        self.assertEqual(
            2,
            workflow.count('".github/workflows/tests.yml"'),
        )
        for test_path in (
            "scripts/test/test-resolve-test-profile.py",
            "scripts/test/test-classify-test-policy.py",
            "scripts/test/test-test-profile-wiring.py",
        ):
            with self.subTest(test_path=test_path):
                self.assertIn(test_path, workflow)


if __name__ == "__main__":
    unittest.main()
