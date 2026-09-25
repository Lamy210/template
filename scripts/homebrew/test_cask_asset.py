from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest

from scripts.homebrew.cask_asset import validate_cask_asset_mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/homebrew/validate-cask-asset.py"


class CaskAssetMappingTests(unittest.TestCase):
    def test_accepts_template_that_expands_to_exact_published_dmg(self) -> None:
        self.assertEqual(
            [],
            validate_cask_asset_mapping(
                source_tag="v1.2.3",
                dmg_name="MyApp-v1.2.3.dmg",
                dmg_basename_template="MyApp-v#{version}.dmg",
            ),
        )

    def test_rejects_template_that_points_to_different_asset(self) -> None:
        errors = validate_cask_asset_mapping(
            source_tag="v1.2.3",
            dmg_name="MyApp-v1.2.3.dmg",
            dmg_basename_template="Other-v#{version}.dmg",
        )

        self.assertTrue(any("must expand exactly to dmg_name" in error for error in errors))

    def test_rejects_noncanonical_or_missing_version_placeholder(self) -> None:
        for template in (
            "MyApp-v1.2.3.dmg",
            "../MyApp-#{version}.dmg",
            "MyApp-#{version}-#{version}.dmg",
        ):
            with self.subTest(template=template):
                errors = validate_cask_asset_mapping(
                    source_tag="v1.2.3",
                    dmg_name="MyApp-v1.2.3.dmg",
                    dmg_basename_template=template,
                )
                self.assertTrue(any("exactly one #{version} placeholder" in error for error in errors))

    def test_rejects_noncanonical_tag_or_dmg_name(self) -> None:
        cases = (
            ("v01.2.3", "MyApp-v1.2.3.dmg"),
            ("v1.2.3", "../MyApp-v1.2.3.dmg"),
        )
        for source_tag, dmg_name in cases:
            with self.subTest(source_tag=source_tag, dmg_name=dmg_name):
                self.assertTrue(
                    validate_cask_asset_mapping(
                        source_tag=source_tag,
                        dmg_name=dmg_name,
                        dmg_basename_template="MyApp-v#{version}.dmg",
                    )
                )

    def test_cli_accepts_exact_mapping(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--source-tag",
                "v1.2.3",
                "--dmg-name",
                "MyApp-v1.2.3.dmg",
                "--dmg-basename-template",
                "MyApp-v#{version}.dmg",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches published DMG", result.stdout)


if __name__ == "__main__":
    unittest.main()
