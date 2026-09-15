import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = ROOT / "scripts/test/classify-test-policy.py"


class TestPolicyClassifierTests(unittest.TestCase):
    def run_classifier(self, **overrides):
        payload = {
            "adapter": "",
            "integrationEnabled": False,
            "integrationRequired": False,
            "coverageEnabled": False,
            "coverageRequired": False,
            "e2eEnabled": False,
            "e2eRequired": False,
        }
        payload.update(overrides)

        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                ["python3", str(CLASSIFIER), "--input", str(input_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            output = json.loads(completed.stdout) if completed.stdout.strip() else None
            return completed, output

    def test_unconfigured_template_is_explicit(self):
        completed, output = self.run_classifier()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(output["configured"])
        self.assertFalse(output["configurationError"])
        self.assertFalse(output["e2eEnabled"])

    def test_xcode_can_enable_e2e(self):
        completed, output = self.run_classifier(
            adapter="xcode", e2eEnabled=True, e2eRequired=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output["configured"])
        self.assertTrue(output["e2eEnabled"])
        self.assertTrue(output["e2eRequired"])

    def test_swiftpm_cannot_enable_macos_e2e(self):
        completed, output = self.run_classifier(adapter="swiftpm", e2eEnabled=True)
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(output["configurationError"])
        self.assertIn("E2E requires the xcode adapter", output["errors"])

    def test_required_disabled_e2e_is_configuration_error(self):
        completed, output = self.run_classifier(adapter="xcode", e2eRequired=True)
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(output["configurationError"])
        self.assertIn("E2E cannot be required while disabled", output["errors"])

    def test_required_disabled_integration_is_configuration_error(self):
        completed, output = self.run_classifier(
            adapter="xcode", integrationRequired=True
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "Integration cannot be required while disabled", output["errors"]
        )

    def test_required_disabled_coverage_is_configuration_error(self):
        completed, output = self.run_classifier(adapter="xcode", coverageRequired=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Coverage cannot be required while disabled", output["errors"])

    def test_invalid_adapter_is_configuration_error(self):
        completed, output = self.run_classifier(adapter="unknown")
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(output["configurationError"])
        self.assertIn("adapter must be xcode, swiftpm, or empty", output["errors"])


if __name__ == "__main__":
    unittest.main()
