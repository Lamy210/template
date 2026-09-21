from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.ci.audit_release_tag_ruleset import validate_live_release_tag_ruleset


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_AUDIT = REPO_ROOT / "scripts/ci/audit-live-release-tag-ruleset.sh"


def valid_live_ruleset() -> dict:
    return {
        "id": 42,
        "name": "Immutable release tags",
        "target": "tag",
        "source_type": "Repository",
        "source": "example/repo",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["refs/tags/v*"],
                "exclude": [],
            }
        },
        "rules": [
            {
                "type": "update",
                "parameters": {"update_allows_fetch_and_merge": False},
            },
            {"type": "deletion"},
        ],
        "node_id": "RRS_example",
        "created_at": "2026-09-21T00:00:00Z",
        "updated_at": "2026-09-21T00:00:00Z",
        "current_user_can_bypass": "never",
        "_links": {"self": {"href": "https://api.github.com/example"}},
    }


class LiveReleaseTagRulesetAuditTests(unittest.TestCase):
    def test_accepts_canonical_live_release_tag_ruleset(self) -> None:
        self.assertEqual(
            [],
            validate_live_release_tag_ruleset(
                valid_live_ruleset(),
                expected_repository="example/repo",
            ),
        )

    def test_rejects_wrong_repository_source(self) -> None:
        document = valid_live_ruleset()
        document["source"] = "example/other"

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("source must equal expected repository" in error for error in errors))

    def test_rejects_parent_or_non_repository_ruleset(self) -> None:
        document = valid_live_ruleset()
        document["source_type"] = "Organization"

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("source_type must equal 'Repository'" in error for error in errors))

    def test_rejects_bypass_actor_or_creation_rule(self) -> None:
        document = valid_live_ruleset()
        document["bypass_actors"] = [
            {"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        ]
        document["rules"].append({"type": "creation"})

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("bypass_actors must be empty" in error for error in errors))
        self.assertTrue(any("unexpected release tag rule types" in error for error in errors))

    def test_cli_accepts_live_ruleset_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = Path(temporary_directory) / "release-tag-ruleset.json"
            payload.write_text(json.dumps(valid_live_ruleset()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/ci/audit_release_tag_ruleset.py",
                    str(payload),
                    "example/repo",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches the immutable release-tag contract", result.stdout)

    def test_live_wrapper_is_read_only_and_targets_tag_rulesets(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("targets=tag", text)
        self.assertIn("includes_parents=true", text)
        self.assertIn("Immutable release tags", text)
        self.assertIn("audit_release_tag_ruleset.py", text)
        for mutation in (
            "--method POST",
            "--method PUT",
            "--method PATCH",
            "--method DELETE",
        ):
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, text)


if __name__ == "__main__":
    unittest.main()
