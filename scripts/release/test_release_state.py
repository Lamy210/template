from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.release_state import (
    validate_release_expectations,
    validate_release_state,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/verify-release-state.py"
EXPECTATIONS_CLI = REPO_ROOT / "scripts/release/validate-release-expectations.py"
TAG = "v1.2.3"
ASSETS = [
    "MyApp-v1.2.3.dmg",
    "MyApp-v1.2.3.dmg.sha256",
    "release-provenance.json",
]


def release_metadata() -> dict[str, object]:
    return {
        "tagName": TAG,
        "isDraft": False,
        "isPrerelease": False,
        "assets": [{"name": name} for name in ASSETS],
    }


class ReleaseStateTests(unittest.TestCase):
    def test_release_expectations_accept_stable_tag_and_exact_safe_assets(self) -> None:
        self.assertEqual(
            [],
            validate_release_expectations(
                expected_tag=TAG,
                expected_asset_names=ASSETS,
            ),
        )

    def test_release_expectations_reject_noncanonical_tag_and_unsafe_assets(self) -> None:
        errors = validate_release_expectations(
            expected_tag="v01.2.3",
            expected_asset_names=["unsafe[asset].dmg", "unsafe[asset].dmg"],
        )
        self.assertTrue(any("stable SemVer" in error for error in errors))
        self.assertTrue(any("unique" in error for error in errors))
        self.assertTrue(any("unsafe" in error for error in errors))

    def test_expectations_cli_rejects_invalid_identity(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(EXPECTATIONS_CLI),
                "--tag=--help",
                "--asset=unsafe[asset].dmg",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("stable SemVer", result.stderr)
        self.assertIn("unsafe or malformed", result.stderr)

    def test_accepts_published_stable_exact_asset_set(self) -> None:
        self.assertEqual(
            [],
            validate_release_state(
                release_metadata(),
                expected_tag=TAG,
                expected_asset_names=ASSETS,
            ),
        )

    def test_rejects_draft_prerelease_and_tag_drift(self) -> None:
        mutations = (
            ("isDraft", True),
            ("isPrerelease", True),
            ("tagName", "v1.2.4"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = release_metadata()
                document[key] = value
                self.assertTrue(
                    validate_release_state(
                        document,
                        expected_tag=TAG,
                        expected_asset_names=ASSETS,
                    )
                )

    def test_rejects_missing_extra_and_duplicate_assets(self) -> None:
        missing = release_metadata()
        missing["assets"] = [{"name": name} for name in ASSETS[:-1]]

        extra = release_metadata()
        extra["assets"] = [
            *[{"name": name} for name in ASSETS],
            {"name": "unexpected.zip"},
        ]

        duplicate = release_metadata()
        duplicate["assets"] = [
            *[{"name": name} for name in ASSETS],
            {"name": ASSETS[0]},
        ]

        for document in (missing, extra, duplicate):
            with self.subTest(document=document):
                errors = validate_release_state(
                    document,
                    expected_tag=TAG,
                    expected_asset_names=ASSETS,
                )
                self.assertTrue(any("asset set" in error for error in errors))

    def test_rejects_malformed_expected_identity(self) -> None:
        errors = validate_release_state(
            release_metadata(),
            expected_tag="v01.2.3",
            expected_asset_names=["../escape.dmg", "../escape.dmg"],
        )
        self.assertTrue(any("stable SemVer" in error for error in errors))
        self.assertTrue(any("unique" in error for error in errors))
        self.assertTrue(any("unsafe" in error for error in errors))

    def test_cli_rejects_release_state_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata = Path(temporary_directory) / "release.json"
            document = release_metadata()
            document["isDraft"] = True
            metadata.write_text(json.dumps(document) + "\n", encoding="utf-8")

            command = [
                sys.executable,
                str(CLI),
                "--metadata",
                str(metadata),
                "--tag",
                TAG,
            ]
            for asset in ASSETS:
                command.extend(["--asset", asset])

            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("published, not draft", result.stderr)


if __name__ == "__main__":
    unittest.main()
