import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "scripts/test/compare-coverage.py"
EXPORT = ROOT / "scripts/test/export-coverage.sh"
PROFILE = "sha256:" + "a" * 64
OTHER_PROFILE = "sha256:" + "b" * 64


def summary(*, profile=PROFILE, covered=800, executable=1000, targets=None):
    targets = targets or {}
    return {
        "schemaVersion": 1,
        "coverageProfileFingerprint": profile,
        "totals": {
            "coveredLines": covered,
            "executableLines": executable,
            "lineCoverage": 0 if executable == 0 else covered / executable,
        },
        "targets": targets,
    }


class CompareCoverageTests(unittest.TestCase):
    def run_compare(self, baseline, current, max_regression="0.001"):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            baseline_path = td / "baseline.json"
            current_path = td / "current.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3",
                    str(COMPARE),
                    "--baseline",
                    str(baseline_path),
                    "--current",
                    str(current_path),
                    "--max-regression",
                    max_regression,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            payload = json.loads(completed.stdout) if completed.stdout.strip() else None
            return completed, payload

    def test_equal_coverage_passes(self):
        completed, payload = self.run_compare(summary(), summary())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "passed")
        self.assertFalse(payload["overall"]["rawCountsChanged"])

    def test_decrease_within_tolerance_passes(self):
        completed, payload = self.run_compare(
            summary(covered=800, executable=1000),
            summary(covered=799, executable=1000),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["status"], "passed")

    def test_substantive_decrease_fails(self):
        completed, payload = self.run_compare(
            summary(covered=800, executable=1000),
            summary(covered=798, executable=1000),
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "regression")
        self.assertTrue(payload["overall"]["regressed"])

    def test_profile_mismatch_requires_migration(self):
        completed, payload = self.run_compare(
            summary(profile=PROFILE),
            summary(profile=OTHER_PROFILE),
        )
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(payload["status"], "migration-required")

    def test_raw_count_and_denominator_changes_are_reported(self):
        completed, payload = self.run_compare(
            summary(covered=800, executable=1000),
            summary(covered=880, executable=1100),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["overall"]["rawCountsChanged"])
        self.assertTrue(payload["overall"]["denominatorChanged"])
        self.assertEqual(payload["overall"]["baseline"]["executableLines"], 1000)
        self.assertEqual(payload["overall"]["current"]["executableLines"], 1100)

    def test_target_regression_is_blocking_when_target_exists_in_both(self):
        baseline_target = {
            "AppCore": {
                "coveredLines": 90,
                "executableLines": 100,
                "lineCoverage": 0.9,
            }
        }
        current_target = {
            "AppCore": {
                "coveredLines": 89,
                "executableLines": 100,
                "lineCoverage": 0.89,
            }
        }
        completed, payload = self.run_compare(
            summary(targets=baseline_target),
            summary(targets=current_target),
            max_regression="0.005",
        )
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(payload["targets"]["AppCore"]["regressed"])

    def test_impossible_raw_counts_are_invalid(self):
        broken = summary(covered=1001, executable=1000)
        completed, payload = self.run_compare(summary(), broken)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["status"], "invalid")
        self.assertIn("coveredLines", payload["error"])


class ExportCoverageTests(unittest.TestCase):
    def run_export(self, adapter, source_payload, profile_payload, *, stub_xcrun=False):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "coverage.json"
            profile = td / "profile.json"
            output = td / "summary.json"
            source.write_text(json.dumps(source_payload), encoding="utf-8")
            profile.write_text(json.dumps(profile_payload), encoding="utf-8")
            env = os.environ.copy()
            input_path = source

            if stub_xcrun:
                bindir = td / "bin"
                bindir.mkdir()
                xcrun = bindir / "xcrun"
                xcrun.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    f"cat {source!s}\n",
                    encoding="utf-8",
                )
                xcrun.chmod(xcrun.stat().st_mode | stat.S_IXUSR)
                env["PATH"] = f"{bindir}:{env['PATH']}"
                input_path = td / "dummy.xcresult"
                input_path.mkdir()

            completed = subprocess.run(
                [
                    "bash",
                    str(EXPORT),
                    "--adapter",
                    adapter,
                    "--input",
                    str(input_path),
                    "--output",
                    str(output),
                    "--profile",
                    str(profile),
                ],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
            return completed, payload

    def test_swiftpm_exporter_normalizes_llvm_json(self):
        fixture = {
            "data": [
                {
                    "totals": {
                        "lines": {"count": 1000, "covered": 812, "percent": 81.2}
                    }
                }
            ],
            "type": "llvm.coverage.json.export",
            "version": "2.0.1",
        }
        completed, payload = self.run_export(
            "swiftpm",
            fixture,
            {"schemaVersion": 1, "toolchain": "swift-6", "excludedTargets": []},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["totals"]["coveredLines"], 812)
        self.assertEqual(payload["totals"]["executableLines"], 1000)
        self.assertAlmostEqual(payload["totals"]["lineCoverage"], 0.812)
        self.assertEqual(payload["targets"], {})
        self.assertRegex(payload["coverageProfileFingerprint"], r"^sha256:[0-9a-f]{64}$")

    def test_xcode_exporter_normalizes_target_raw_counts(self):
        fixture = {
            "coveredLines": 256,
            "executableLines": 4106,
            "lineCoverage": 256 / 4106,
            "targets": [
                {
                    "name": "AppCore",
                    "coveredLines": 200,
                    "executableLines": 300,
                    "lineCoverage": 2 / 3,
                },
                {
                    "name": "UITests",
                    "coveredLines": 56,
                    "executableLines": 3806,
                    "lineCoverage": 56 / 3806,
                },
            ],
        }
        completed, payload = self.run_export(
            "xcode",
            fixture,
            {"schemaVersion": 1, "toolchain": "Xcode 26.6"},
            stub_xcrun=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["totals"]["coveredLines"], 256)
        self.assertEqual(payload["targets"]["AppCore"]["coveredLines"], 200)
        self.assertEqual(payload["targets"]["UITests"]["executableLines"], 3806)

    def test_profile_fingerprint_is_stable_across_json_key_order(self):
        fixture = {
            "data": [{"totals": {"lines": {"count": 10, "covered": 8, "percent": 80}}}]
        }
        first, first_payload = self.run_export(
            "swiftpm",
            fixture,
            {"schemaVersion": 1, "toolchain": "swift-6", "includedTargets": ["Core"]},
        )
        second, second_payload = self.run_export(
            "swiftpm",
            fixture,
            {"includedTargets": ["Core"], "toolchain": "swift-6", "schemaVersion": 1},
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(
            first_payload["coverageProfileFingerprint"],
            second_payload["coverageProfileFingerprint"],
        )

    def test_exporter_rejects_impossible_counts(self):
        fixture = {
            "data": [{"totals": {"lines": {"count": 10, "covered": 11, "percent": 110}}}]
        }
        completed, payload = self.run_export(
            "swiftpm",
            fixture,
            {"schemaVersion": 1, "toolchain": "swift-6"},
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIsNone(payload)


if __name__ == "__main__":
    unittest.main()
