from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.ci.repository_merge_settings import (
    RepositoryMergeSettings,
    validate_repository_merge_settings,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/ci/validate-repository-merge-settings.py"
DOCTOR = REPO_ROOT / "scripts/ci/audit-live-repository-merge-settings.sh"
QUALITY = REPO_ROOT / ".github/workflows/quality.yml"
SETUP = REPO_ROOT / "docs/SETUP.md"
BRANCHING = REPO_ROOT / "docs/BRANCHING.md"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"


def valid_metadata() -> dict[str, object]:
    return {
        "id": 1367784801,
        "full_name": "Lamy210/template",
        "allow_squash_merge": True,
        "allow_merge_commit": False,
        "allow_rebase_merge": False,
        "delete_branch_on_merge": True,
    }


class RepositoryMergeSettingsTests(unittest.TestCase):
    def test_accepts_documented_merge_policy(self) -> None:
        errors, settings = validate_repository_merge_settings(
            valid_metadata(),
            expected_repository="Lamy210/template",
        )

        self.assertEqual([], errors)
        self.assertEqual(
            RepositoryMergeSettings(
                repository_id=1367784801,
                full_name="Lamy210/template",
                allow_squash_merge=True,
                allow_merge_commit=False,
                allow_rebase_merge=False,
                delete_branch_on_merge=True,
            ),
            settings,
        )

    def test_repository_name_comparison_is_case_insensitive(self) -> None:
        errors, settings = validate_repository_merge_settings(
            valid_metadata(),
            expected_repository="lamy210/TEMPLATE",
        )

        self.assertEqual([], errors)
        self.assertIsNotNone(settings)

    def test_rejects_each_merge_policy_drift(self) -> None:
        cases = (
            ("allow_squash_merge", False, "must equal true"),
            ("allow_merge_commit", True, "must equal false"),
            ("allow_rebase_merge", True, "must equal false"),
            ("delete_branch_on_merge", False, "must equal true"),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                document = valid_metadata()
                document[field] = value
                errors, settings = validate_repository_merge_settings(
                    document,
                    expected_repository="Lamy210/template",
                )
                self.assertIsNone(settings)
                self.assertTrue(
                    any(field in error and expected in error for error in errors),
                    errors,
                )

    def test_rejects_malformed_or_wrong_repository_identity(self) -> None:
        cases = (
            ([], "JSON object"),
            ({**valid_metadata(), "id": 0}, "positive integer"),
            ({**valid_metadata(), "full_name": "../escape"}, "canonical owner/repo"),
            (
                {**valid_metadata(), "full_name": "Lamy210/other"},
                "does not match",
            ),
            (
                {**valid_metadata(), "allow_squash_merge": 1},
                "must be a boolean",
            ),
        )
        for document, expected in cases:
            with self.subTest(expected=expected):
                errors, settings = validate_repository_merge_settings(
                    document,
                    expected_repository="Lamy210/template",
                )
                self.assertIsNone(settings)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_cli_reports_closed_desired_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata = Path(temporary_directory) / "repository.json"
            metadata.write_text(
                json.dumps({**valid_metadata(), "future_field": "ignored"}) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(metadata),
                    "--repository",
                    "Lamy210/template",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "repository_id=1367784801",
                "repository=lamy210/template",
                "allow_squash_merge=true",
                "allow_merge_commit=false",
                "allow_rebase_merge=false",
                "delete_branch_on_merge=true",
            ],
            result.stdout.splitlines(),
        )

    def test_documentation_matches_merge_policy_contract(self) -> None:
        expected_lines = (
            "- squash merge: enabled",
            "- merge commits: disabled",
            "- rebase merge: disabled",
            "- delete head branches after merge: enabled",
        )
        for path in (SETUP, BRANCHING):
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                for line in expected_lines:
                    self.assertIn(line, text)
                self.assertIn(
                    "bash scripts/ci/audit-live-repository-merge-settings.sh",
                    text,
                )

        setup = SETUP.read_text(encoding="utf-8")
        self.assertIn(
            "bash scripts/setup/apply-repository-merge-settings.sh",
            setup,
        )
        self.assertIn("--confirm-repository owner/repo", setup)
        self.assertIn("--apply", setup)

        contributing = CONTRIBUTING.read_text(encoding="utf-8")
        self.assertIn("Use squash merge", contributing)
        self.assertIn(
            "disables merge commits and rebase merges",
            contributing,
        )

    def test_live_doctor_is_read_only_and_rebinds_state(self) -> None:
        text = DOCTOR.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count('"repos/' + '$' + '{repository}"'), 2)
        self.assertIn(
            "Repository identity or merge settings changed during the audit",
            text,
        )
        for forbidden in (
            "--method PUT",
            "--method POST",
            "--method PATCH",
            "--method DELETE",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_quality_requires_repository_merge_policy_regressions(self) -> None:
        text = QUALITY.read_text(encoding="utf-8")
        self.assertIn("scripts.ci.test_repository_merge_settings", text)
        self.assertIn(
            "bash scripts/ci/test-audit-live-repository-merge-settings.sh",
            text,
        )


if __name__ == "__main__":
    unittest.main()
