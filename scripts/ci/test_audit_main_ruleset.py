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
                        {"context": "Tests / Required Gate"},
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

    def test_accepts_repository_source_with_different_casing(self) -> None:
        document = valid_live_ruleset()
        document["source"] = "Example/Repo"

        self.assertEqual(
            [],
            validate_live_main_ruleset(
                document,
                expected_repository="EXAMPLE/REPO",
            ),
        )

    def test_rejects_noncanonical_repository_identities(self) -> None:
        for repository in ("../escape", "./repo", "owner/..", "owner/."):
            with self.subTest(repository=repository):
                document = valid_live_ruleset()
                document["source"] = repository

                errors = validate_live_main_ruleset(
                    document,
                    expected_repository=repository,
                )

                self.assertTrue(
                    any("canonical owner/repo" in error for error in errors),
                    errors,
                )

    def test_cli_rejects_noncanonical_repository_before_reading_input(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ci/audit_main_ruleset.py",
                "/definitely/missing/ruleset.json",
                "../escape",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("canonical owner/repo", result.stderr)
        self.assertNotIn("failed to read", result.stderr)

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
                    if endpoint == "repos/example/repo":
                        print(json.dumps({{
                            "id": 101,
                            "full_name": "example/repo",
                            "default_branch": "main",
                        }}))
                        raise SystemExit(0)
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

    def test_live_wrapper_accepts_canonical_github_casing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            detail = valid_live_ruleset()
            detail["source"] = "Example/Repo"
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
                    if endpoint == "repos/EXAMPLE/REPO":
                        print(json.dumps({{
                            "id": 101,
                            "full_name": "Example/Repo",
                            "default_branch": "main",
                        }}))
                        raise SystemExit(0)
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
                ["bash", str(LIVE_AUDIT), "EXAMPLE/REPO"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches the Solo default-branch contract", result.stdout)

    def test_live_wrapper_rejects_final_ruleset_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            detail_before = root / "ruleset-before.json"
            detail_after = root / "ruleset-after.json"
            count_file = root / "ruleset-count"

            detail = valid_live_ruleset()
            drifted = valid_live_ruleset()
            drifted["name"] = "Drifted"
            summary = {
                "id": detail["id"],
                "name": detail["name"],
                "target": detail["target"],
                "source_type": detail["source_type"],
                "source": detail["source"],
                "enforcement": detail["enforcement"],
            }
            detail_before.write_text(
                json.dumps(detail) + "\n",
                encoding="utf-8",
            )
            detail_after.write_text(
                json.dumps(drifted) + "\n",
                encoding="utf-8",
            )

            fake_gh.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import json
                    import os
                    from pathlib import Path
                    import sys

                    endpoint = sys.argv[-1]
                    if endpoint == "repos/example/repo":
                        print(json.dumps({{
                            "id": 101,
                            "full_name": "example/repo",
                            "default_branch": "main",
                        }}))
                        raise SystemExit(0)
                    if "rulesets?targets=branch&includes_parents=true&per_page=100" in endpoint:
                        print(json.dumps([[{summary!r}]]))
                        raise SystemExit(0)
                    if endpoint.endswith("rulesets/84?includes_parents=true"):
                        count_file = Path(os.environ["GH_FAKE_RULESET_COUNT_FILE"])
                        count = int(count_file.read_text() or "0") if count_file.exists() else 0
                        count += 1
                        count_file.write_text(str(count))
                        detail_path = (
                            os.environ["GH_FAKE_RULESET_BEFORE"]
                            if count == 1
                            else os.environ["GH_FAKE_RULESET_AFTER"]
                        )
                        print(Path(detail_path).read_text(), end="")
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
            env["GH_FAKE_RULESET_COUNT_FILE"] = str(count_file)
            env["GH_FAKE_RULESET_BEFORE"] = str(detail_before)
            env["GH_FAKE_RULESET_AFTER"] = str(detail_after)
            result = subprocess.run(
                ["bash", str(LIVE_AUDIT), "example/repo"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("name must equal 'Solo default branch'", result.stderr)
        self.assertEqual("2", count_file.read_text())

    def test_live_wrapper_rejects_repository_snapshot_drift(self) -> None:
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
                    import os
                    from pathlib import Path
                    import sys

                    endpoint = sys.argv[-1]
                    if endpoint == "repos/example/repo":
                        count_file = Path(os.environ["GH_FAKE_COUNT_FILE"])
                        count = int(count_file.read_text() or "0") if count_file.exists() else 0
                        count += 1
                        count_file.write_text(str(count))
                        repository_id = 101
                        default_branch = "main"
                        scenario = os.environ.get("GH_FAKE_SCENARIO", "success")
                        if count >= 2 and scenario == "identity-drift":
                            repository_id = 202
                        if count >= 2 and scenario == "branch-drift":
                            default_branch = "develop"
                        print(json.dumps({{
                            "id": repository_id,
                            "full_name": "example/repo",
                            "default_branch": default_branch,
                        }}))
                        raise SystemExit(0)

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

            for scenario, expected_success in (
                ("success", True),
                ("identity-drift", False),
                ("branch-drift", False),
            ):
                with self.subTest(scenario=scenario):
                    count_file = root / f"count-{scenario}"
                    env = os.environ.copy()
                    env["PATH"] = f"{root}:{env['PATH']}"
                    env["GH_FAKE_SCENARIO"] = scenario
                    env["GH_FAKE_COUNT_FILE"] = str(count_file)
                    result = subprocess.run(
                        ["bash", str(LIVE_AUDIT), "example/repo"],
                        cwd=REPO_ROOT,
                        env=env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                    if expected_success:
                        self.assertEqual(0, result.returncode, result.stderr)
                        self.assertIn(
                            "matches the Solo default-branch contract",
                            result.stdout,
                        )
                    else:
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(
                            "Repository identity or default branch changed",
                            result.stderr,
                        )

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
