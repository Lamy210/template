from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "scripts/test/resolve-test-profile.py"
MAX_JSON_BYTES = 2 * 1024 * 1024
SENTINEL_OUTPUT = "sentinel=keep\n"


def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resolver = load_script("resolve_test_profile", "scripts/test/resolve-test-profile.py")
classifier = load_script("classify_test_policy", "scripts/test/classify-test-policy.py")


def payload(
    *,
    profile: str,
    adapter: str,
    integration_enabled: bool | None = None,
    integration_required: bool | None = None,
    coverage_enabled: bool | None = None,
    coverage_required: bool | None = None,
    e2e_enabled: bool | None = None,
    e2e_required: bool | None = None,
    visual_enabled: bool | None = None,
    visual_required: bool | None = None,
    visual_bootstrap: bool | None = None,
) -> dict[str, object]:
    return {
        "profile": profile,
        "adapter": adapter,
        "integrationEnabled": integration_enabled,
        "integrationRequired": integration_required,
        "coverageEnabled": coverage_enabled,
        "coverageRequired": coverage_required,
        "e2eEnabled": e2e_enabled,
        "e2eRequired": e2e_required,
        "visualEnabled": visual_enabled,
        "visualRequired": visual_required,
        "visualBootstrap": visual_bootstrap,
    }


def write_oversized_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


POLICY_FIELDS = (
    "integrationEnabled",
    "integrationRequired",
    "coverageEnabled",
    "coverageRequired",
    "e2eEnabled",
    "e2eRequired",
    "visualEnabled",
    "visualRequired",
    "visualBootstrap",
)
EXPECTED = {
    "minimal": (False, False, False, False, False, False, False, False, False),
    "standard": (False, False, True, True, False, False, False, False, False),
    "macos-app": (False, False, True, True, True, True, False, False, False),
    "macos-ui-strict": (False, False, True, True, True, True, True, True, False),
}


class TestProfileResolverTests(unittest.TestCase):
    def run_cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(RESOLVER),
                "--input",
                str(root / "input.json"),
                "--output",
                str(root / "output.json"),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_named_profile_defaults_are_deterministic(self) -> None:
        for profile, expected in EXPECTED.items():
            with self.subTest(profile=profile):
                adapter = "xcode" if profile.startswith("macos-") else "swiftpm"
                result = resolver.resolve(payload(profile=profile, adapter=adapter))
                self.assertEqual(
                    expected,
                    tuple(result[field] for field in POLICY_FIELDS),
                )

    def test_output_contains_only_classifier_contract_fields(self) -> None:
        result = resolver.resolve(payload(profile="standard", adapter="swiftpm"))
        self.assertEqual(classifier.EXPECTED_KEYS, set(result))

    def test_legacy_coverage_enabled_defaults_required_true(self) -> None:
        result = resolver.resolve(
            payload(profile="", adapter="swiftpm", coverage_enabled=True)
        )
        self.assertTrue(result["coverageEnabled"])
        self.assertTrue(result["coverageRequired"])

    def test_legacy_visual_enabled_defaults_required_true(self) -> None:
        result = resolver.resolve(
            payload(
                profile="",
                adapter="xcode",
                e2e_enabled=True,
                visual_enabled=True,
            )
        )
        self.assertTrue(result["visualEnabled"])
        self.assertTrue(result["visualRequired"])

    def test_macos_app_e2e_can_be_made_optional(self) -> None:
        result = resolver.resolve(
            payload(
                profile="macos-app",
                adapter="xcode",
                e2e_required=False,
            )
        )
        self.assertTrue(result["e2eEnabled"])
        self.assertFalse(result["e2eRequired"])

    def test_disabling_e2e_does_not_implicitly_clear_required(self) -> None:
        result = resolver.resolve(
            payload(
                profile="macos-app",
                adapter="xcode",
                e2e_enabled=False,
            )
        )
        self.assertFalse(result["e2eEnabled"])
        self.assertTrue(result["e2eRequired"])

    def test_explicit_visual_bootstrap_is_preserved(self) -> None:
        result = resolver.resolve(
            payload(
                profile="macos-ui-strict",
                adapter="xcode",
                visual_bootstrap=True,
            )
        )
        self.assertTrue(result["visualBootstrap"])

    def test_unknown_profile_fails_closed(self) -> None:
        with self.assertRaisesRegex(resolver.InputError, "unsupported test profile"):
            resolver.resolve(payload(profile="everything", adapter="xcode"))

    def test_xcode_only_profile_rejects_swiftpm(self) -> None:
        with self.assertRaisesRegex(resolver.InputError, "requires the xcode adapter"):
            resolver.resolve(payload(profile="macos-app", adapter="swiftpm"))

    def test_named_profile_requires_configured_adapter(self) -> None:
        with self.assertRaisesRegex(resolver.InputError, "require adapter"):
            resolver.resolve(payload(profile="standard", adapter=""))

    def test_malformed_environment_boolean_fails_closed(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MACOS_TEST_PROFILE": "standard",
                "MACOS_TEST_ADAPTER": "swiftpm",
                "MACOS_COVERAGE_ENABLED": "yes",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                resolver.InputError,
                "MACOS_COVERAGE_ENABLED must be true, false, or empty",
            ):
                resolver.load_environment()

    def test_profile_required_while_disabled_is_rejected_by_classifier(self) -> None:
        resolved = resolver.resolve(
            payload(
                profile="macos-app",
                adapter="xcode",
                e2e_enabled=False,
            )
        )
        code, classified = classifier.classify(resolved)
        self.assertEqual(classifier.EXIT_CONFIGURATION_ERROR, code)
        self.assertIn("E2E cannot be required while disabled", classified["errors"])

    def test_visual_profile_still_requires_e2e(self) -> None:
        resolved = resolver.resolve(
            payload(
                profile="macos-ui-strict",
                adapter="xcode",
                e2e_enabled=False,
                e2e_required=False,
            )
        )
        code, classified = classifier.classify(resolved)
        self.assertEqual(classifier.EXIT_CONFIGURATION_ERROR, code)
        self.assertIn("Visual requires E2E to be enabled", classified["errors"])

    def test_cli_writes_deterministic_classifier_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            output_path = root / "output.json"
            input_path.write_text(
                json.dumps(payload(profile="standard", adapter="swiftpm")),
                encoding="utf-8",
            )

            completed = self.run_cli(root)

            self.assertEqual(0, completed.returncode, completed.stderr)
            raw = output_path.read_text(encoding="utf-8")
            self.assertTrue(raw.endswith("\n"))
            self.assertEqual(
                resolver.resolve(payload(profile="standard", adapter="swiftpm")),
                json.loads(raw),
            )

    def test_cli_rejects_oversized_json_input_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            output_path = root / "output.json"
            write_oversized_json(
                input_path,
                payload(profile="standard", adapter="swiftpm"),
            )
            output_path.write_text(SENTINEL_OUTPUT, encoding="utf-8")

            completed = self.run_cli(root)

            self.assertEqual(2, completed.returncode)
            self.assertIn("JSON byte limit", completed.stderr)
            self.assertEqual(
                SENTINEL_OUTPUT,
                output_path.read_text(encoding="utf-8"),
            )

    def test_cli_rejects_symlinked_json_input_without_writing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            target_path = root / "input-target.json"
            output_path = root / "output.json"
            target_path.write_text(
                json.dumps(payload(profile="standard", adapter="swiftpm")),
                encoding="utf-8",
            )
            input_path.symlink_to(target_path)
            output_path.write_text(SENTINEL_OUTPUT, encoding="utf-8")

            completed = self.run_cli(root)

            self.assertEqual(2, completed.returncode)
            self.assertIn("non-symlink", completed.stderr)
            self.assertEqual(
                SENTINEL_OUTPUT,
                output_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
