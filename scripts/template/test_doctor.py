from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTOR = REPO_ROOT / "scripts/template/doctor.sh"

CORE_CHECKS = (
    "scripts/ci/audit-live-repository-merge-settings.sh",
    "scripts/ci/audit-live-main-ruleset.sh",
    "scripts/ci/audit-live-main-rules.sh",
    "scripts/ci/audit-live-release-tag-ruleset.sh",
)
RELEASE_CHECKS = CORE_CHECKS + (
    "scripts/release/audit-release-environment.sh",
    "scripts/ci/audit-live-immutable-releases.sh",
)


class TemplateDoctorTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> Path:
        doctor = root / "scripts/template/doctor.sh"
        doctor.parent.mkdir(parents=True)
        shutil.copy2(DOCTOR, doctor)

        stub = """#!/usr/bin/env bash
set -euo pipefail
name="$(basename "$0")"
printf '%s|%s\\n' "${name}" "${1:-}" >>"${DOCTOR_LOG:?}"
if [[ "${name}" == "${FAIL_CHECK:-}" ]]; then
  exit 17
fi
printf 'stub pass: %s\\n' "${name}"
"""
        for relative_path in RELEASE_CHECKS:
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(stub, encoding="utf-8")
            path.chmod(0o755)
        return doctor

    def run_doctor(
        self,
        doctor: Path,
        log: Path,
        *,
        profile: str = "core",
        repository: str = "Example/Repo",
        fail_check: str = "",
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["DOCTOR_LOG"] = str(log)
        if fail_check:
            environment["FAIL_CHECK"] = fail_check
        else:
            environment.pop("FAIL_CHECK", None)
        return subprocess.run(
            [
                "bash",
                str(doctor),
                "--repository",
                repository,
                "--profile",
                profile,
            ],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

    def test_core_profile_runs_exact_read_only_governance_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            doctor = self.build_fixture(root)
            log = root / "doctor.log"
            result = self.run_doctor(doctor, log)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(
                "template doctor: 4/4 checks passed for Example/Repo (profile=core)",
                result.stdout,
            )
            invocations = log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            [
                f"{Path(path).name}|Example/Repo"
                for path in CORE_CHECKS
            ],
            invocations,
        )

    def test_release_profile_adds_environment_and_immutable_release_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            doctor = self.build_fixture(root)
            log = root / "doctor.log"
            result = self.run_doctor(doctor, log, profile="release")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn(
                "template doctor: 6/6 checks passed for Example/Repo (profile=release)",
                result.stdout,
            )
            invocations = log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            [
                f"{Path(path).name}|Example/Repo"
                for path in RELEASE_CHECKS
            ],
            invocations,
        )

    def test_failure_is_aggregated_without_skipping_later_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            doctor = self.build_fixture(root)
            log = root / "doctor.log"
            result = self.run_doctor(
                doctor,
                log,
                fail_check="audit-live-main-rules.sh",
            )
            invocations = log.read_text(encoding="utf-8").splitlines()

        self.assertEqual(1, result.returncode)
        self.assertIn(
            "[FAIL] Effective default-branch rules (exit 17)",
            result.stderr,
        )
        self.assertIn(
            "template doctor: 3/4 checks passed for Example/Repo (profile=core)",
            result.stdout,
        )
        self.assertEqual(4, len(invocations))

    def test_invalid_input_fails_before_any_check_runs(self) -> None:
        for repository, profile, expected in (
            ("../escape", "core", "canonical owner/repo"),
            ("Example/Repo", "unknown", "--profile must be either core or release"),
        ):
            with self.subTest(repository=repository, profile=profile):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    doctor = self.build_fixture(root)
                    log = root / "doctor.log"
                    result = self.run_doctor(
                        doctor,
                        log,
                        profile=profile,
                        repository=repository,
                    )

                    self.assertEqual(2, result.returncode)
                    self.assertIn(expected, result.stderr)
                    self.assertFalse(log.exists())

    def test_missing_check_fails_preflight_before_any_check_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            doctor = self.build_fixture(root)
            missing = root / CORE_CHECKS[2]
            missing.unlink()
            log = root / "doctor.log"
            result = self.run_doctor(doctor, log)

            self.assertEqual(2, result.returncode)
            self.assertIn("unavailable or is a symlink", result.stderr)
            self.assertFalse(log.exists())

    def test_orchestrator_has_no_direct_github_mutation_surface(self) -> None:
        text = DOCTOR.read_text(encoding="utf-8")
        for forbidden in (
            "gh api",
            "--method POST",
            "--method PUT",
            "--method PATCH",
            "--method DELETE",
            "apply-repository-merge-settings.sh",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

        for path in RELEASE_CHECKS:
            self.assertIn(f'"{path}"', text)


if __name__ == "__main__":
    unittest.main()
