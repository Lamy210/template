from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/test/emit-profile-adoption-outputs.py"
MAX_JSON_BYTES = 2 * 1024 * 1024
SENTINEL_OUTPUT = "sentinel=keep\n"


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


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class EmitProfileAdoptionOutputsTests(unittest.TestCase):
    def write_cli_inputs(
        self, root: Path
    ) -> tuple[dict[str, tuple[Path, dict[str, object]]], Path]:
        inputs = {
            "resolved policy": (root / "resolved.json", resolved()),
            "classified policy": (root / "classified.json", classified()),
        }
        for path, payload in inputs.values():
            path.write_text(json.dumps(payload), encoding="utf-8")
        output_path = root / "github-output.txt"
        output_path.write_text(SENTINEL_OUTPUT, encoding="utf-8")
        return inputs, output_path

    def run_cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--resolved",
                str(root / "resolved.json"),
                "--classified",
                str(root / "classified.json"),
                "--github-output",
                str(root / "github-output.txt"),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

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
            _inputs, output_path = self.write_cli_inputs(root)
            output_path.write_text("", encoding="utf-8")
            completed = self.run_cli(root)

            self.assertEqual(0, completed.returncode, completed.stderr)
            lines = output_path.read_text(encoding="utf-8").splitlines()
            self.assertIn("adapter=swiftpm", lines)
            self.assertIn("coverage_enabled=true", lines)
            self.assertIn("visual_bootstrap=false", lines)

    def test_cli_rejects_oversized_json_inputs_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels = ("resolved policy", "classified policy")

            for index, label in enumerate(labels):
                with self.subTest(label=label):
                    case_root = root / f"oversized-{index}"
                    case_root.mkdir()
                    inputs, output_path = self.write_cli_inputs(case_root)
                    path, payload = inputs[label]
                    write_oversized_json(path, payload)

                    completed = self.run_cli(case_root)

                    self.assertEqual(2, completed.returncode)
                    self.assertIn("JSON byte limit", completed.stderr)
                    self.assertEqual(
                        SENTINEL_OUTPUT,
                        output_path.read_text(encoding="utf-8"),
                    )

    def test_cli_rejects_symlinked_json_inputs_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            labels = ("resolved policy", "classified policy")

            for index, label in enumerate(labels):
                with self.subTest(label=label):
                    case_root = root / f"symlink-{index}"
                    case_root.mkdir()
                    inputs, output_path = self.write_cli_inputs(case_root)
                    path, _payload = inputs[label]
                    target = path.with_name(path.stem + "-target.json")
                    path.replace(target)
                    path.symlink_to(target)

                    completed = self.run_cli(case_root)

                    self.assertEqual(2, completed.returncode)
                    self.assertIn("non-symlink", completed.stderr)
                    self.assertEqual(
                        SENTINEL_OUTPUT,
                        output_path.read_text(encoding="utf-8"),
                    )


if __name__ == "__main__":
    unittest.main()
