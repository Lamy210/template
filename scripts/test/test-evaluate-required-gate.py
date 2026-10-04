import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = ROOT / "scripts/test/evaluate-required-gate.py"
EXPECTED = ("Unit", "Integration", "E2E", "Visual", "Coverage")
MAX_JSON_BYTES = 2 * 1024 * 1024


def record(status="success", required=False, classification="applicable"):
    return {
        "status": status,
        "required": required,
        "classification": classification,
    }


def policy(**overrides):
    subsystems = {
        name: record(status="disabled", classification="not-applicable")
        for name in EXPECTED
    }
    subsystems.update(overrides)
    return {"schemaVersion": 1, "subsystems": subsystems}


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class RequiredGateTests(unittest.TestCase):
    def run_gate_path(self, path: Path):
        completed = subprocess.run(
            [sys.executable, str(EVALUATOR), "--input", str(path)],
            text=True,
            capture_output=True,
            check=False,
        )
        output = json.loads(completed.stdout) if completed.stdout.strip() else None
        return completed, output

    def run_gate(self, payload):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return self.run_gate_path(path)

    def test_required_success_passes(self):
        completed, output = self.run_gate(policy(Unit=record(required=True)))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["status"], "passed")
        self.assertEqual(output["blocking"], [])

    def test_required_failure_blocks(self):
        completed, output = self.run_gate(
            policy(Unit=record(status="failure", required=True))
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(output["status"], "failed")
        self.assertIn("Unit", output["blocking"][0])

    def test_unexpected_cancelled_status_blocks(self):
        completed, output = self.run_gate(
            policy(Unit=record(status="cancelled", required=True))
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(output["status"], "failed")
        self.assertIn("unexpected status", output["blocking"][0])

    def test_missing_subsystem_result_blocks(self):
        payload = policy(Unit=record(required=True))
        del payload["subsystems"]["Unit"]
        completed, output = self.run_gate(payload)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(output["status"], "failed")
        self.assertIn("missing result", output["blocking"][0])

    def test_optional_failure_is_visible_but_non_blocking(self):
        completed, output = self.run_gate(
            policy(Integration=record(status="failure", required=False))
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["status"], "passed")
        self.assertIn("Integration", output["warnings"][0])

    def test_required_not_applicable_passes_only_with_explicit_classification(self):
        completed, output = self.run_gate(
            policy(
                E2E=record(
                    status="not-applicable",
                    required=True,
                    classification="not-applicable",
                )
            )
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["status"], "passed")

        completed, output = self.run_gate(
            policy(
                E2E=record(
                    status="not-applicable",
                    required=True,
                    classification="applicable",
                )
            )
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(output["status"], "configuration-error")

    def test_disabled_required_subsystem_is_configuration_error(self):
        completed, output = self.run_gate(
            policy(
                Visual=record(
                    status="disabled",
                    required=True,
                    classification="not-applicable",
                )
            )
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(output["status"], "configuration-error")
        self.assertIn("required", output["configurationErrors"][0])

    def test_all_optional_disabled_is_explicit_not_configured_bootstrap(self):
        completed, output = self.run_gate(policy())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["status"], "not-configured")

    def test_unknown_subsystem_is_configuration_error(self):
        payload = policy()
        payload["subsystems"]["Performance"] = record()
        completed, output = self.run_gate(payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(output["status"], "configuration-error")

    def test_cli_rejects_oversized_input_as_configuration_error(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "policy.json"
            write_oversized_json(path, policy())

            completed, output = self.run_gate_path(path)

        self.assertEqual(2, completed.returncode)
        self.assertEqual("configuration-error", output["status"])
        self.assertIn("JSON byte limit", output["configurationErrors"][0])

    def test_cli_rejects_symlinked_input_as_configuration_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "policy.json"
            target = root / "policy-target.json"
            target.write_text(json.dumps(policy()), encoding="utf-8")
            path.symlink_to(target)

            completed, output = self.run_gate_path(path)

        self.assertEqual(2, completed.returncode)
        self.assertEqual("configuration-error", output["status"])
        self.assertIn("non-symlink", output["configurationErrors"][0])


if __name__ == "__main__":
    unittest.main()
