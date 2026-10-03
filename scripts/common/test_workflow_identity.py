from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.common.bounded_json import DEFAULT_MAX_JSON_BYTES
from scripts.common.workflow_identity import (
    WorkflowIdentity,
    is_safe_workflow_filename,
    validate_workflow_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/common/validate-workflow-identity.py"


def valid_metadata() -> dict[str, object]:
    return {
        "id": 358957647,
        "name": "Tests",
        "path": ".github/workflows/tests.yml",
        "state": "active",
    }


class WorkflowIdentityTests(unittest.TestCase):
    def test_accepts_safe_workflow_file_names(self) -> None:
        for value in ("tests.yml", "visual-regression.yaml", "CI Tests.yml"):
            with self.subTest(value=value):
                self.assertTrue(is_safe_workflow_filename(value))

    def test_rejects_unsafe_workflow_selectors(self) -> None:
        for value in (
            "",
            ".",
            "..",
            "tests",
            "tests.json",
            ".github/workflows/tests.yml",
            "../tests.yml",
            "tests\\evil.yml",
            " tests.yml",
            "tests.yml ",
            "tests.yml?event=push",
            "tests.yml\nother.yml",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_safe_workflow_filename(value))

    def test_accepts_exact_workflow_identity(self) -> None:
        errors, identity = validate_workflow_identity(
            valid_metadata(),
            expected_workflow="tests.yml",
        )

        self.assertEqual([], errors)
        self.assertEqual(
            WorkflowIdentity(
                workflow_id=358957647,
                path=".github/workflows/tests.yml",
            ),
            identity,
        )

    def test_rejects_malformed_or_mismatched_identity(self) -> None:
        cases = (
            ([], "tests.yml", "JSON object"),
            ({**valid_metadata(), "id": 0}, "tests.yml", "positive integer"),
            (
                {**valid_metadata(), "path": ".github/workflows/other.yml"},
                "tests.yml",
                "does not match",
            ),
            (
                valid_metadata(),
                "../tests.yml",
                "safe .yml/.yaml",
            ),
        )
        for document, expected_workflow, expected_error in cases:
            with self.subTest(expected_error=expected_error):
                errors, identity = validate_workflow_identity(
                    document,
                    expected_workflow=expected_workflow,
                )
                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_cli_prints_id_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata = Path(temporary_directory) / "workflow.json"
            metadata.write_text(json.dumps(valid_metadata()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(metadata),
                    "--workflow",
                    "tests.yml",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["358957647", ".github/workflows/tests.yml"],
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
                    "--workflow",
                    "tests.yml",
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
                    "--workflow",
                    "tests.yml",
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
