from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from scripts.ci.audit_main_ruleset import validate_live_main_ruleset


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_AUDIT = REPO_ROOT / "scripts/ci/audit-live-main-ruleset.sh"


def valid_live_ruleset() -> dict:
    return {
        "id": 84,
        "name": "Solo default branch",
        "target": "branch",
        "source_type": "Repository",
        "source": "example/repo",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": "Required gate"},
                        {"context": "swift-quality / Swift quality"},
                    ],
                },
            },
        ],
        "node_id": "RRS_example",
        "created_at": "2026-09-22T00:00:00Z",
        "updated_at": "2026-09-22T00:00:00Z",
        "current_user_can_bypass": "never",
        "_links": {"self": {"href": "https://api.github.com/example"}},
    }


class LiveMainRulesetAuditTests(unittest.TestCase):
    def test_accepts_canonical_live_main_ruleset(self) -> None:
        self.assertEqual(
            [],
            validate_live_main_ruleset(
                valid_live_ruleset(),
                expected_repository="example/repo",
            ),
        )

    def test_rejects_broad_release_branch_targeting(self) -> None:
        document = valid_live_ruleset()
        document["conditions"]["ref_name"]["include"].append("refs/heads/release**")

        errors = validate_live_main_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("ref_name.include must equal ['~DEFAULT_BRANCH']" in error for error in errors))

    def test_rejects_wrong_source_or_non_repository_ruleset(self) -> None:
        document = valid_live_ruleset()
        document["source"] = "example/other"
        document["source_type"] = "Organization"

        errors = validate_live_main_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("source must equal expected repository" in error for error in errors))
        self.assertTrue(any("source_type must equal 'Repository'" in error for error in errors))

    def test_rejects_bypass_actor_and_current_user_bypass(self) -> None:
        document = valid_live_ruleset()
        document["bypass_actors"] = [
            {"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        ]
        document["current_user_can_bypass"] = "always"

        errors = validate_live_main_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("bypass_actors must be empty" in error for error in errors))
        self.assertTrue(any("current_user_can_bypass must equal 'never'" in error for error in errors))

    def test_cli_accepts_live_ruleset_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = Path(temporary_directory) / "main-ruleset.json"
            payload.write_text(json.dumps(valid_live_ruleset()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/ci/audit_main_ruleset.py",
                    str(payload),
                    "example/repo",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches the Solo default-branch contract", result.stdout)

    def test_live_wrapper_reads_list_and_exact_ruleset_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            detail = valid_live_ruleset()
            summary = {
                "id": detail["id"],
                "name": detail["name"],
                "target": detail["target"],
                "source_type": detail["source_type"],
                "source": detail["source"],
                "enforcement": detail["enforcement"],
            }
            fake_gh.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import json
                    import sys

                    endpoint = sys.argv[-1]
                    if "rulesets?targets=branch&includes_parents=true&per_page=100" in endpoint:
                        print(json.dumps([[{summary!r}]]))
                        raise SystemExit(0)
                    if endpoint.endswith("rulesets/84?includes_parents=true"):
                        print(json.dumps({detail!r}))
                        raise SystemExit(0)
                    print("unexpected endpoint: " + endpoint, file=sys.stderr)
                    raise SystemExit(9)
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{root}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(LIVE_AUDIT), "example/repo"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches the Solo default-branch contract", result.stdout)

    def test_live_wrapper_is_read_only_and_fetches_named_branch_ruleset(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("targets=branch", text)
        self.assertIn("includes_parents=true", text)
        self.assertIn("Solo default branch", text)
        self.assertIn("audit_main_ruleset.py", text)
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
