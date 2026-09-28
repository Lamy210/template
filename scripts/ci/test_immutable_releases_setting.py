from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.ci.immutable_releases_setting import (
    ImmutableReleasesSetting,
    validate_immutable_releases_setting,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/ci/validate-immutable-releases-setting.py"
DOCTOR = REPO_ROOT / "scripts/ci/audit-live-immutable-releases.sh"


class ImmutableReleasesSettingTests(unittest.TestCase):
    def test_accepts_repository_enabled_setting(self) -> None:
        errors, setting = validate_immutable_releases_setting(
            {"enabled": True, "enforced_by_owner": False}
        )

        self.assertEqual([], errors)
        self.assertEqual(
            ImmutableReleasesSetting(
                enabled=True,
                enforced_by_owner=False,
            ),
            setting,
        )

    def test_accepts_owner_enforced_setting(self) -> None:
        errors, setting = validate_immutable_releases_setting(
            {"enabled": True, "enforced_by_owner": True}
        )

        self.assertEqual([], errors)
        self.assertIsNotNone(setting)
        assert setting is not None
        self.assertTrue(setting.enforced_by_owner)

    def test_rejects_disabled_or_malformed_setting(self) -> None:
        cases = (
            ({"enabled": False, "enforced_by_owner": False}, "must be enabled"),
            ({"enabled": "true", "enforced_by_owner": False}, "boolean true"),
            ({"enabled": True, "enforced_by_owner": None}, "enforced_by_owner"),
            ([], "JSON object"),
        )
        for document, expected in cases:
            with self.subTest(document=document):
                errors, setting = validate_immutable_releases_setting(document)
                self.assertIsNone(setting)
                self.assertTrue(
                    any(expected in error for error in errors),
                    errors,
                )

    def test_live_doctor_is_read_only_and_rebinds_repository_identity(self) -> None:
        text = DOCTOR.read_text(encoding="utf-8")
        self.assertIn('"repos/${repository}/immutable-releases"', text)
        self.assertIn("Administration(read)", text)
        self.assertGreaterEqual(text.count('"repos/${repository}"'), 2)
        self.assertIn("Repository identity changed during immutable-release audit", text)
        for forbidden in (
            "--method PUT",
            "--method POST",
            "--method PATCH",
            "--method DELETE",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_cli_reports_closed_two_line_setting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata = Path(temporary_directory) / "setting.json"
            metadata.write_text(
                json.dumps(
                    {
                        "enabled": True,
                        "enforced_by_owner": True,
                        "future_field": "ignored",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(metadata),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["enabled=true", "enforced_by_owner=true"],
            result.stdout.splitlines(),
        )


if __name__ == "__main__":
    unittest.main()
