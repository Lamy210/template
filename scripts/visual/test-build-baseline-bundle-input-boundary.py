import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/visual/build-baseline-bundle.py"
PROFILE_ID = "macos-26-arm64-xcode-26.6"
SOURCE_SHA = "a" * 40
MAX_JSON_BYTES = 2 * 1024 * 1024


def load_builder():
    spec = importlib.util.spec_from_file_location("baseline_builder_boundary", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load baseline builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def controlled_profile():
    return {
        "runnerFamily": "macos-26",
        "architecture": "ARM64",
        "xcodePolicy": "Xcode 26.6",
        "locale": "en_US.UTF-8",
        "language": "en",
        "timezone": "UTC",
        "appearance": "controlled-by-test",
        "displayScale": "2x",
        "captureGeometry": "window-or-element",
        "fixtureVersion": "fixture-v1",
        "captureContractVersion": 1,
        "comparatorSchemaVersion": 1,
    }


def profile_payload():
    controlled = controlled_profile()
    canonical = json.dumps(
        controlled,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schemaVersion": 2,
        "profile": PROFILE_ID,
        "controlled": controlled,
        "observed": {},
        "profileFingerprint": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "currentSHA": SOURCE_SHA,
    }


def manifest_payload():
    return {
        "schemaVersion": 1,
        "profile": PROFILE_ID,
        "cases": [],
    }


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class BaselineBundleInputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / "Tests/VisualRegression").mkdir(parents=True)
        (self.repo / "artifacts/visual").mkdir(parents=True)
        self.manifest = self.repo / "Tests/VisualRegression/visual-regression.json"
        self.profile = self.repo / "artifacts/visual/profile.json"
        self.output = self.repo / "out/visual-baseline"
        self.manifest.write_text(json.dumps(manifest_payload()), encoding="utf-8")
        self.profile.write_text(json.dumps(profile_payload()), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        module = load_builder()
        module.build_bundle(
            repo_root=self.repo,
            manifest_path=self.manifest,
            current_profile_path=self.profile,
            output_root=self.output,
            repository="Lamy210/template",
            workflow="tests.yml",
            run_id="12345",
            run_attempt=1,
            source_sha=SOURCE_SHA,
            previous_baseline_reference=None,
        )

    def test_rejects_oversized_manifest_before_output(self):
        write_oversized_json(self.manifest, manifest_payload())

        with self.assertRaisesRegex(ValueError, "JSON byte limit"):
            self.build()

        self.assertFalse(self.output.exists())

    def test_rejects_oversized_profile_before_output(self):
        write_oversized_json(self.profile, profile_payload())

        with self.assertRaisesRegex(ValueError, "JSON byte limit"):
            self.build()

        self.assertFalse(self.output.exists())

    def test_rejects_symlinked_manifest_before_output(self):
        target = self.manifest.with_name("visual-regression-target.json")
        self.manifest.replace(target)
        self.manifest.symlink_to(target)

        with self.assertRaisesRegex(ValueError, "non-symlink"):
            self.build()

        self.assertFalse(self.output.exists())

    def test_rejects_symlinked_profile_before_output(self):
        target = self.profile.with_name("profile-target.json")
        self.profile.replace(target)
        self.profile.symlink_to(target)

        with self.assertRaisesRegex(ValueError, "non-symlink"):
            self.build()

        self.assertFalse(self.output.exists())

    def test_direct_cli_remains_package_safe(self):
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
