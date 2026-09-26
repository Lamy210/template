from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/test/emit-profile-adoption-outputs.py"


def load_script():
    spec = importlib.util.spec_from_file_location("emit_profile_adoption_outputs", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = load_script()


def resolved(*, adapter: str = "swiftpm", coverage: bool = True) -> dict[str, object]:
    return {
        "adapter": adapter,
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": coverage,
        "coverageRequired": coverage,
        "e2eEnabled": adapter == "xcode",
        "e2eRequired": adapter == "xcode",
        "visualEnabled": False,
        "visualRequired": False,
        "visualBootstrap": False,
    }


def classified(*, adapter: str = "swiftpm", coverage: bool = True) -> dict[str, object]:
    return {
        **resolved(adapter=adapter, coverage=coverage),
        "configured": True,
        "configurationError": False,
        "errors": [],
    }


class EmitProfileAdoptionOutputsTests(unittest.TestCase):
    def test_accepts_valid_swiftpm_policy(self) -> None:
        values = bridge.emit_values(resolved(), classified())
        self.assertEqual("swiftpm", values["adapter"])
        self.assertEqual("true", values["coverage_enabled"])
        self.assertEqual("false", values["e2e_enabled"])

    def test_accepts_valid_xcode_policy(self) -> None:
        values = bridge.emit_values(
            resolved(adapter="xcode"),
            classified(adapter="xcode"),
        )
        self.assertEqual("xcode", values["adapter"])
        self.assertEqual("true", values["e2e_enabled"])
        self.assertEqual("true", values["e2e_required"])

    def test_rejects_missing_keys(self) -> None:
        policy = resolved()
        policy.pop("visualRequired")
        with self.assertRaisesRegex(bridge.InputError, "missing key"):
            bridge.emit_values(policy, classified())

    def test_rejects_configuration_error(self) -> None:
        policy = classified()
        policy["configurationError"] = True
        policy["errors"] = ["bad"]
        with self.assertRaisesRegex(bridge.InputError, "configuration error"):
            bridge.emit_values(resolved(), policy)

    def test_rejects_non_boolean_policy_value(self) -> None:
        policy = resolved()
        policy["coverageEnabled"] = "true"
        with self.assertRaisesRegex(bridge.InputError, "must be boolean"):
            bridge.emit_values(policy, classified())

    def test_rejects_adapter_disagreement(self) -> None:
        with self.assertRaisesRegex(bridge.InputError, "adapter mismatch"):
            bridge.emit_values(resolved(), classified(adapter="xcode"))

    def test_rejects_policy_disagreement(self) -> None:
        policy = classified()
        policy["coverageRequired"] = False
        with self.assertRaisesRegex(bridge.InputError, "policy mismatch"):
            bridge.emit_values(resolved(), policy)

    def test_cli_emits_lowercase_scalar_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolved_path = root / "resolved.json"
            classified_path = root / "classified.json"
            output_path = root / "github-output.txt"
            resolved_path.write_text(json.dumps(resolved()), encoding="utf-8")
            classified_path.write_text(json.dumps(classified()), encoding="utf-8")
            output_path.write_text("", encoding="utf-8")

            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--resolved",
                    str(resolved_path),
                    "--classified",
                    str(classified_path),
                    "--github-output",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertIn("adapter=swiftpm", lines)
            self.assertIn("coverage_enabled=true", lines)
            self.assertIn("visual_bootstrap=false", lines)


if __name__ == "__main__":
    unittest.main()
