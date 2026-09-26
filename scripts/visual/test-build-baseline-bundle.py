import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/visual/build-baseline-bundle.py"
PROFILE_ID = "macos-26-arm64-xcode-26.6"
SOURCE_SHA = "a" * 40


def load_builder():
    spec = importlib.util.spec_from_file_location("baseline_builder", MODULE_PATH)
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
        controlled, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schemaVersion": 2,
        "profile": PROFILE_ID,
        "controlled": controlled,
        "observed": {
            "macOSBuild": "25G83",
            "runnerImageVersion": "test-image",
            "xcodeBuild": "Xcode 26.6 | Build version 17G86",
        },
        "profileFingerprint": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "currentSHA": SOURCE_SHA,
    }


class BaselineBundleBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        (self.repo / "Tests/VisualRegression").mkdir(parents=True)
        (self.repo / "artifacts/visual/current").mkdir(parents=True)
        self.manifest = self.repo / "Tests/VisualRegression/visual-regression.json"
        self.profile = self.repo / "artifacts/visual/profile.json"
        self.output = self.repo / "out/visual-baseline"
        self.manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "profile": PROFILE_ID,
                    "cases": [
                        {
                            "id": "git-case",
                            "baseline": "git",
                            "current": "artifacts/visual/current/git-case.png",
                            "expected": "Tests/VisualBaselines/profile/git-case.png",
                            "maxChangedPixelRatio": 0.0,
                            "maxChannelDelta": 0,
                        },
                        {
                            "id": "rolling-case",
                            "baseline": "rolling-main",
                            "current": "artifacts/visual/current/rolling-case.png",
                            "maxChangedPixelRatio": 0.001,
                            "maxChannelDelta": 8,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.profile.write_text(json.dumps(profile_payload()), encoding="utf-8")
        (self.repo / "artifacts/visual/current/git-case.png").write_bytes(b"git-image")
        (self.repo / "artifacts/visual/current/rolling-case.png").write_bytes(b"rolling-image")

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
            run_attempt=2,
            source_sha=SOURCE_SHA,
            previous_baseline_reference="run:12000",
        )

    def test_builds_only_rolling_cases(self):
        self.build()
        manifest = json.loads((self.output / "bundle-manifest.json").read_text())
        self.assertEqual([case["id"] for case in manifest["cases"]], ["rolling-case"])
        expected = "sha256:" + hashlib.sha256(b"rolling-image").hexdigest()
        self.assertEqual(manifest["cases"][0]["digest"], expected)
        self.assertEqual((self.output / "images/rolling-case.png").read_bytes(), b"rolling-image")
        self.assertFalse((self.output / "images/git-case.png").exists())
        self.assertEqual(
            json.loads((self.output / "profile.json").read_text()), profile_payload()
        )

    def test_records_provenance(self):
        self.build()
        manifest = json.loads((self.output / "bundle-manifest.json").read_text())
        self.assertEqual(manifest["sourceRepository"], "Lamy210/template")
        self.assertEqual(manifest["workflow"], "tests.yml")
        self.assertEqual(manifest["sourceRunID"], "12345")
        self.assertEqual(manifest["runAttempt"], 2)
        self.assertEqual(manifest["sourceSHA"], SOURCE_SHA)
        self.assertEqual(manifest["previousBaselineReference"], "run:12000")

    def test_rejects_existing_output(self):
        self.output.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "output"):
            self.build()

    def test_rejects_symlink_output_before_resolving_destination(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        redirected = self.repo / "redirected" / "visual-baseline"
        self.output.symlink_to(redirected, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "symlink"):
            self.build()

        self.assertTrue(self.output.is_symlink())
        self.assertFalse(redirected.exists())

    def test_rejects_tampered_profile_fingerprint(self):
        payload = profile_payload()
        payload["profileFingerprint"] = "sha256:" + "0" * 64
        self.profile.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_rejects_profile_label_mismatch(self):
        payload = profile_payload()
        payload["profile"] = "different-profile"
        self.profile.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "profile label"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_rejects_current_sha_mismatch(self):
        payload = profile_payload()
        payload["currentSHA"] = "b" * 40
        self.profile.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "currentSHA"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_rejects_capture_outside_visual_root(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["cases"][1]["current"] = "outside.png"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        (self.repo / "outside.png").write_bytes(b"outside")
        with self.assertRaisesRegex(ValueError, "capture root"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_rejects_invalid_provenance_before_writing_output(self):
        module = load_builder()
        with self.assertRaisesRegex(ValueError, "repository"):
            module.build_bundle(
                repo_root=self.repo,
                manifest_path=self.manifest,
                current_profile_path=self.profile,
                output_root=self.output,
                repository="invalid",
                workflow="tests.yml",
                run_id="12345",
                run_attempt=2,
                source_sha=SOURCE_SHA,
                previous_baseline_reference=None,
            )
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
