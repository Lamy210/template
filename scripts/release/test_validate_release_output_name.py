from __future__ import annotations

import subprocess
import sys
import unittest

from scripts.release.release_output_name import validate_dmg_name


class ReleaseOutputNameTests(unittest.TestCase):
    def test_accepts_safe_literal_dmg_basenames(self) -> None:
        for value in (
            "MyApp-1.2.3.dmg",
            "My_App+build.dmg",
            "app.dmg",
        ):
            with self.subTest(value=value):
                self.assertEqual([], validate_dmg_name(value))

    def test_rejects_path_like_or_non_dmg_names(self) -> None:
        for value in (
            "",
            "../escape.dmg",
            "nested/MyApp.dmg",
            r"nested\MyApp.dmg",
            ".hidden.dmg",
            "My App.dmg",
            "MyApp",
            "MyApp.zip",
        ):
            with self.subTest(value=value):
                self.assertTrue(validate_dmg_name(value))

    def test_cli_rejects_unsafe_name(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/validate-release-output-name.py",
                "--dmg-name",
                "../escape.dmg",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("safe literal .dmg basename", result.stderr)

    def test_cli_accepts_safe_name(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/validate-release-output-name.py",
                "--dmg-name",
                "MyApp-1.2.3.dmg",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
