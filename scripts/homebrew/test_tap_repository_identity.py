from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.homebrew.tap_repository_identity import (
    validate_tap_repository_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/homebrew/tap_repository_identity.py"


def repository_document() -> dict[str, object]:
    return {
        "id": 123,
        "full_name": "Example/homebrew-tap",
        "default_branch": "main",
        "clone_url": "https://github.com/Example/homebrew-tap.git",
        "ssh_url": "git@github.com:Example/homebrew-tap.git",
    }


class TapRepositoryIdentityTests(unittest.TestCase):
    def test_accepts_canonical_repository_snapshot(self) -> None:
        errors, identity = validate_tap_repository_identity(
            repository_document(),
            expected_repository="example/HOMEBREW-tap",
            expected_default_branch="main",
        )

        self.assertEqual([], errors)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(123, identity["repositoryId"])
        self.assertEqual("Example/homebrew-tap", identity["fullName"])

    def test_rebind_requires_same_numeric_repository_id(self) -> None:
        errors, identity = validate_tap_repository_identity(
            repository_document(),
            expected_repository="Example/homebrew-tap",
            expected_default_branch="main",
            expected_repository_id=124,
        )

        self.assertIsNone(identity)
        self.assertTrue(
            any("trusted repository snapshot" in error for error in errors)
        )

    def test_rejects_repository_name_or_default_branch_drift(self) -> None:
        cases = [
            (
                {**repository_document(), "full_name": "Example/other-tap"},
                "full_name",
            ),
            (
                {**repository_document(), "default_branch": "trunk"},
                "default_branch",
            ),
        ]
        for document, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                errors, identity = validate_tap_repository_identity(
                    document,
                    expected_repository="Example/homebrew-tap",
                    expected_default_branch="main",
                    expected_repository_id=123,
                )
                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_rejects_boolean_or_nonpositive_repository_ids(self) -> None:
        for repository_id in (True, 0, -1, "123"):
            with self.subTest(repository_id=repository_id):
                errors, identity = validate_tap_repository_identity(
                    {**repository_document(), "id": repository_id},
                    expected_repository="Example/homebrew-tap",
                    expected_default_branch="main",
                )
                self.assertIsNone(identity)
                self.assertTrue(any("positive integer" in error for error in errors))

    def test_rejects_repository_urls_that_do_not_match_full_name(self) -> None:
        cases = (
            (
                "clone_url",
                "https://github.com/Example/other-tap.git",
                "clone_url",
            ),
            (
                "clone_url",
                "https://token@github.com/Example/homebrew-tap.git",
                "clone_url",
            ),
            (
                "clone_url",
                "http://github.com/Example/homebrew-tap.git",
                "clone_url",
            ),
            (
                "ssh_url",
                "git@github.com:Example/other-tap.git",
                "ssh_url",
            ),
            (
                "ssh_url",
                "ssh://git@github.com/Example/homebrew-tap.git",
                "ssh_url",
            ),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                errors, identity = validate_tap_repository_identity(
                    {**repository_document(), field: value},
                    expected_repository="Example/homebrew-tap",
                    expected_default_branch="main",
                )
                self.assertIsNone(identity)
                self.assertTrue(
                    any(
                        expected_error in error
                        and "canonical full_name" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_rejects_malformed_canonical_urls(self) -> None:
        for field, value in (
            ("clone_url", ""),
            ("clone_url", "https://github.com/Example/homebrew-tap.git\nother"),
            ("ssh_url", None),
        ):
            with self.subTest(field=field, value=value):
                errors, identity = validate_tap_repository_identity(
                    {**repository_document(), field: value},
                    expected_repository="Example/homebrew-tap",
                    expected_default_branch="main",
                )
                self.assertIsNone(identity)
                self.assertTrue(any(field in error for error in errors))

    def test_cli_emits_closed_five_line_identity_tuple(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata = Path(temporary_directory) / "repository.json"
            metadata.write_text(
                json.dumps(repository_document()),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--metadata",
                    str(metadata),
                    "--repository",
                    "example/homebrew-tap",
                    "--default-branch",
                    "main",
                    "--repository-id",
                    "123",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "123",
                "Example/homebrew-tap",
                "main",
                "https://github.com/Example/homebrew-tap.git",
                "git@github.com:Example/homebrew-tap.git",
            ],
            result.stdout.splitlines(),
        )


if __name__ == "__main__":
    unittest.main()
