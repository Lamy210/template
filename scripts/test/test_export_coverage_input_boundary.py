from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "scripts/test/export-coverage.sh"


def swiftpm_coverage() -> dict[str, object]:
    return {
        "data": [
            {
                "totals": {
                    "lines": {
                        "count": 10,
                        "covered": 8,
                        "percent": 80,
                    }
                }
            }
        ],
        "type": "llvm.coverage.json.export",
        "version": "2.0.1",
    }


def coverage_profile() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "toolchain": "swift-6",
    }


class ExportCoverageInputBoundaryTests(unittest.TestCase):
    def run_export(
        self,
        input_path: Path,
        profile_path: Path,
        output_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                str(EXPORT),
                "--adapter",
                "swiftpm",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--profile",
                str(profile_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_rejects_symlinked_swiftpm_coverage_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            real_input = root / "coverage-real.json"
            real_input.write_text(json.dumps(swiftpm_coverage()), encoding="utf-8")
            input_path = root / "coverage.json"
            input_path.symlink_to(real_input.name)
            profile = root / "profile.json"
            profile.write_text(json.dumps(coverage_profile()), encoding="utf-8")
            output = root / "summary.json"

            result = self.run_export(input_path, profile, output)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("regular non-symlink file", result.stderr)
            self.assertFalse(output.exists())

    def test_rejects_symlinked_coverage_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_path = root / "coverage.json"
            input_path.write_text(json.dumps(swiftpm_coverage()), encoding="utf-8")
            real_profile = root / "profile-real.json"
            real_profile.write_text(json.dumps(coverage_profile()), encoding="utf-8")
            profile = root / "profile.json"
            profile.symlink_to(real_profile.name)
            output = root / "summary.json"

            result = self.run_export(input_path, profile, output)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("regular non-symlink file", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
