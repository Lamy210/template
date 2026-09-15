import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/test/run-macos-e2e.sh"
DIAGNOSTICS = ROOT / "scripts/test/export-e2e-diagnostics.sh"


class MacOSE2EToolingTests(unittest.TestCase):
    def make_executable(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def base_environment(self, root: Path, bindir: Path, log: Path) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{bindir}:{env['PATH']}",
                "XCODEBUILD_LOG": str(log),
                "GITHUB_WORKSPACE": str(root / "repo"),
                "RUNNER_TEMP": str(root / "runner"),
                "WORKING_DIRECTORY": ".",
                "PROJECT_PATH": "App.xcodeproj",
                "WORKSPACE_PATH": "",
                "SCHEME": "App",
                "TEST_PLAN": "E2E",
                "TEST_DESTINATION": "platform=macOS,arch=arm64",
            }
        )
        return env

    def install_xcodebuild_stub(self, bindir: Path) -> None:
        self.make_executable(
            bindir / "xcodebuild",
            """#!/usr/bin/env bash
set -euo pipefail
printf '%s|seed=%s|time=%s|animations=%s|visual=%s\\n' \
  "$*" "${TEST_RANDOM_SEED:-}" "${TEST_FIXED_TIME:-}" \
  "${TEST_DISABLE_ANIMATIONS:-}" "${VISUAL_OUTPUT_DIR:-}" >>"${XCODEBUILD_LOG}"
if [[ "$*" == *"test-without-building"* ]]; then
  previous=""
  for argument in "$@"; do
    if [[ "${previous}" == "-resultBundlePath" ]]; then
      mkdir -p "${argument}"
      break
    fi
    previous="${argument}"
  done
fi
""",
        )

    def test_runner_builds_before_testing_with_deterministic_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindir = root / "bin"
            repo = root / "repo"
            runner_temp = root / "runner"
            project = repo / "App.xcodeproj"
            bindir.mkdir()
            project.mkdir(parents=True)
            runner_temp.mkdir()
            log = root / "xcodebuild.log"
            self.install_xcodebuild_stub(bindir)
            env = self.base_environment(root, bindir, log)

            completed = subprocess.run(
                ["bash", str(RUNNER)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            lines = log.read_text(encoding="utf-8").splitlines()
            build_index = next(i for i, line in enumerate(lines) if "build-for-testing" in line)
            test_index = next(i for i, line in enumerate(lines) if "test-without-building" in line)
            self.assertLess(build_index, test_index)
            self.assertIn("seed=0", lines[test_index])
            self.assertIn("time=2026-01-01T00:00:00Z", lines[test_index])
            self.assertIn("animations=1", lines[test_index])
            self.assertTrue((repo / "artifacts/visual/current").is_dir())
            self.assertTrue((runner_temp / "e2e.xcresult").is_dir())

    def test_runner_rejects_project_and_workspace_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindir = root / "bin"
            repo = root / "repo"
            runner_temp = root / "runner"
            (repo / "App.xcodeproj").mkdir(parents=True)
            (repo / "App.xcworkspace").mkdir()
            bindir.mkdir()
            runner_temp.mkdir()
            log = root / "xcodebuild.log"
            self.install_xcodebuild_stub(bindir)
            env = self.base_environment(root, bindir, log)
            env["WORKSPACE_PATH"] = "App.xcworkspace"

            completed = subprocess.run(
                ["bash", str(RUNNER)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertFalse(log.exists())

    def test_diagnostics_exporter_exports_attachments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindir = root / "bin"
            runner_temp = root / "runner"
            bindir.mkdir()
            runner_temp.mkdir()
            (runner_temp / "e2e.xcresult").mkdir()
            self.make_executable(
                bindir / "xcrun",
                """#!/usr/bin/env bash
set -euo pipefail
previous=""
for argument in "$@"; do
  if [[ "${previous}" == "--output-path" ]]; then
    mkdir -p "${argument}"
    printf 'attachment\\n' >"${argument}/sample.txt"
    exit 0
  fi
  previous="${argument}"
done
exit 8
""",
            )
            env = os.environ.copy()
            env["PATH"] = f"{bindir}:{env['PATH']}"
            env["RUNNER_TEMP"] = str(runner_temp)

            completed = subprocess.run(
                ["bash", str(DIAGNOSTICS)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((runner_temp / "e2e-attachments/sample.txt").is_file())

    def test_diagnostics_exporter_accepts_missing_result_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runner_temp = Path(temporary) / "runner"
            runner_temp.mkdir()
            env = os.environ.copy()
            env["RUNNER_TEMP"] = str(runner_temp)

            completed = subprocess.run(
                ["bash", str(DIAGNOSTICS)],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("skipped", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()
