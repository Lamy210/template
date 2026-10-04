import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = ROOT / "scripts/test/classify-test-policy.py"
MAX_JSON_BYTES = 2 * 1024 * 1024


def policy_payload(**overrides):
    payload = {
        "adapter": "",
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": False,
        "coverageRequired": False,
        "e2eEnabled": False,
        "e2eRequired": False,
        "visualEnabled": False,
        "visualRequired": False,
        "visualBootstrap": False,
    }
    payload.update(overrides)
    return payload


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


def read_github_output(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    )


class TestPolicyClassifierTests(unittest.TestCase):
    def run_classifier_path(
        self,
        input_path: Path,
        *,
        github_output: Path | None = None,
    ):
        command = [sys.executable, str(CLASSIFIER), "--input", str(input_path)]
        if github_output is not None:
            command.extend(["--github-output", str(github_output)])
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout) if completed.stdout.strip() else None
        return completed, output

    def run_classifier(self, **overrides):
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "input.json"
            input_path.write_text(
                json.dumps(policy_payload(**overrides)),
                encoding="utf-8",
            )
            return self.run_classifier_path(input_path)

    def run_classifier_from_env(self, **overrides):
        env = os.environ.copy()
        policy_variables = (
            "MACOS_TEST_ADAPTER",
            "MACOS_INTEGRATION_ENABLED",
            "MACOS_INTEGRATION_REQUIRED",
            "MACOS_COVERAGE_ENABLED",
            "MACOS_COVERAGE_REQUIRED",
            "MACOS_E2E_ENABLED",
            "MACOS_E2E_REQUIRED",
            "MACOS_VISUAL_ENABLED",
            "MACOS_VISUAL_REQUIRED",
            "MACOS_VISUAL_BOOTSTRAP",
        )
        for name in policy_variables:
            env.pop(name, None)
        env.update(overrides)

        completed = subprocess.run(
            [sys.executable, str(CLASSIFIER), "--from-env"],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        output = json.loads(completed.stdout) if completed.stdout.strip() else None
        return completed, output

    def assert_fail_closed_github_output(self, path: Path) -> None:
        values = read_github_output(path)
        self.assertEqual("false", values["configured"])
        self.assertEqual("true", values["configuration_error"])
        for name in (
            "integration_enabled",
            "integration_required",
            "coverage_enabled",
            "coverage_required",
            "e2e_enabled",
            "e2e_required",
            "visual_enabled",
            "visual_required",
            "visual_bootstrap",
        ):
            with self.subTest(output=name):
                self.assertEqual("false", values[name])

    def test_unconfigured_template_is_explicit(self):
        completed, output = self.run_classifier()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(output["configured"])
        self.assertFalse(output["configurationError"])
        self.assertFalse(output["e2eEnabled"])
        self.assertFalse(output["visualEnabled"])

    def test_xcode_can_enable_e2e(self):
        completed, output = self.run_classifier(
            adapter="xcode", e2eEnabled=True, e2eRequired=True
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output["configured"])
        self.assertTrue(output["e2eEnabled"])
        self.assertTrue(output["e2eRequired"])

    def test_xcode_e2e_can_enable_required_visual_bootstrap(self):
        completed, output = self.run_classifier(
            adapter="xcode",
            e2eEnabled=True,
            visualEnabled=True,
            visualRequired=True,
            visualBootstrap=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output["visualEnabled"])
        self.assertTrue(output["visualRequired"])
        self.assertTrue(output["visualBootstrap"])

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

    def test_required_disabled_visual_is_configuration_error(self):
        completed, output = self.run_classifier(adapter="xcode", visualRequired=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Visual cannot be required while disabled", output["errors"])

    def test_visual_requires_e2e_capture(self):
        completed, output = self.run_classifier(adapter="xcode", visualEnabled=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Visual requires E2E to be enabled", output["errors"])

    def test_visual_bootstrap_requires_visual_enabled(self):
        completed, output = self.run_classifier(adapter="xcode", visualBootstrap=True)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Visual bootstrap requires Visual to be enabled", output["errors"])

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

    def test_malformed_enabled_environment_boolean_fails_closed(self):
        completed, output = self.run_classifier_from_env(
            MACOS_TEST_ADAPTER="xcode",
            MACOS_E2E_ENABLED="tru",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(output["configurationError"])
        self.assertIn(
            "MACOS_E2E_ENABLED must be true, false, or empty",
            output["errors"],
        )

    def test_malformed_required_environment_boolean_fails_closed(self):
        completed, output = self.run_classifier_from_env(
            MACOS_TEST_ADAPTER="xcode",
            MACOS_COVERAGE_ENABLED="true",
            MACOS_COVERAGE_REQUIRED="yes",
        )
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(output["configurationError"])
        self.assertIn(
            "MACOS_COVERAGE_REQUIRED must be true, false, or empty",
            output["errors"],
        )

    def test_environment_coverage_required_defaults_to_enabled_state(self):
        completed, output = self.run_classifier_from_env(
            MACOS_TEST_ADAPTER="swiftpm",
            MACOS_COVERAGE_ENABLED="true",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output["coverageEnabled"])
        self.assertTrue(output["coverageRequired"])

    def test_environment_coverage_required_explicit_false_is_preserved(self):
        completed, output = self.run_classifier_from_env(
            MACOS_TEST_ADAPTER="swiftpm",
            MACOS_COVERAGE_ENABLED="true",
            MACOS_COVERAGE_REQUIRED="false",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(output["coverageEnabled"])
        self.assertFalse(output["coverageRequired"])

    def test_invalid_adapter_is_configuration_error(self):
        completed, output = self.run_classifier(adapter="unknown")
        self.assertEqual(completed.returncode, 2)
        self.assertTrue(output["configurationError"])
        self.assertIn("adapter must be xcode, swiftpm, or empty", output["errors"])

    def test_cli_rejects_oversized_input_and_publishes_fail_closed_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            github_output = root / "github-output.txt"
            write_oversized_json(
                input_path,
                policy_payload(
                    adapter="xcode",
                    coverageEnabled=True,
                    coverageRequired=True,
                ),
            )

            completed, output = self.run_classifier_path(
                input_path,
                github_output=github_output,
            )

            self.assertEqual(2, completed.returncode)
            self.assertTrue(output["configurationError"])
            self.assertIn("JSON byte limit", output["errors"][0])
            self.assert_fail_closed_github_output(github_output)

    def test_cli_rejects_symlinked_input_and_publishes_fail_closed_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            target_path = root / "input-target.json"
            github_output = root / "github-output.txt"
            target_path.write_text(
                json.dumps(
                    policy_payload(
                        adapter="xcode",
                        coverageEnabled=True,
                        coverageRequired=True,
                    )
                ),
                encoding="utf-8",
            )
            input_path.symlink_to(target_path)

            completed, output = self.run_classifier_path(
                input_path,
                github_output=github_output,
            )

            self.assertEqual(2, completed.returncode)
            self.assertTrue(output["configurationError"])
            self.assertIn("non-symlink", output["errors"][0])
            self.assert_fail_closed_github_output(github_output)


if __name__ == "__main__":
    unittest.main()
