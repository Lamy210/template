from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.common.bounded_json import DEFAULT_MAX_JSON_BYTES
from scripts.common.repository_identity import (
    RepositoryIdentity,
    validate_repository_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/common/validate-repository-identity.py"


def valid_metadata() -> dict[str, object]:
    return {
        "id": 1367784801,
        "full_name": "Lamy210/template",
    }


class RepositoryIdentityTests(unittest.TestCase):
    def test_accepts_stable_repository_identity_case_insensitively(self) -> None:
        errors, identity = validate_repository_identity(
            valid_metadata(),
            expected_repository="lamy210/TEMPLATE",
        )

        self.assertEqual([], errors)
        self.assertEqual(
            RepositoryIdentity(
                repository_id=1367784801,
                full_name="Lamy210/template",
            ),
            identity,
        )

    def test_rejects_malformed_or_mismatched_identity(self) -> None:
        cases = (
            ([], "Lamy210/template", "JSON object"),
            ({**valid_metadata(), "id": 0}, "Lamy210/template", "positive integer"),
            (
                {**valid_metadata(), "full_name": "../escape"},
                "Lamy210/template",
                "canonical owner/repo",
            ),
            (
                valid_metadata(),
                "../escape",
                "expected repository must use canonical owner/repo",
            ),
            (
                {**valid_metadata(), "full_name": "Lamy210/other"},
                "Lamy210/template",
                "does not match",
            ),
        )
        for document, expected_repository, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                errors, identity = validate_repository_identity(
                    document,
                    expected_repository=expected_repository,
                )
                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_cli_prints_id_and_canonical_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata = Path(temporary_directory) / "repository.json"
            metadata.write_text(json.dumps(valid_metadata()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(metadata),
                    "--repository",
                    "lamy210/TEMPLATE",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["1367784801", "Lamy210/template"],
            result.stdout.splitlines(),
        )

    def test_cli_rejects_oversized_and_symlinked_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            oversized = root / "oversized.json"
            with oversized.open("wb") as handle:
                handle.truncate(DEFAULT_MAX_JSON_BYTES + 1)

            oversized_result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(oversized),
                    "--repository",
                    "Lamy210/template",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, oversized_result.returncode)
            self.assertIn("JSON byte limit", oversized_result.stderr)

            real = root / "real.json"
            real.write_text(json.dumps(valid_metadata()) + "\n", encoding="utf-8")
            symlink = root / "symlink.json"
            symlink.symlink_to(real.name)
            symlink_result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(symlink),
                    "--repository",
                    "Lamy210/template",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, symlink_result.returncode)
            self.assertIn("regular non-symlink file", symlink_result.stderr)


if __name__ == "__main__":
    unittest.main()
