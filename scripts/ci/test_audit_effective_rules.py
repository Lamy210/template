from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from scripts.ci.audit_effective_rules import validate_effective_main_rules


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_AUDIT = REPO_ROOT / "scripts/ci/audit-live-main-rules.sh"


def desired_rules() -> list[dict]:
    return [
        {
            "type": "deletion",
            "ruleset_id": 100,
            "ruleset_source_type": "Repository",
            "ruleset_source": "example/repo",
        },
        {
            "type": "non_fast_forward",
            "ruleset_id": 100,
            "ruleset_source_type": "Repository",
            "ruleset_source": "example/repo",
        },
        {
            "type": "required_linear_history",
            "ruleset_id": 100,
            "ruleset_source_type": "Repository",
            "ruleset_source": "example/repo",
        },
        {
            "type": "pull_request",
            "ruleset_id": 100,
            "ruleset_source_type": "Repository",
            "ruleset_source": "example/repo",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": True,
                "allowed_merge_methods": ["squash"],
                "required_reviewers": [],
                "require_extra_approval_for_unattributed_changes": False,
            },
        },
        {
            "type": "required_status_checks",
            "ruleset_id": 100,
            "ruleset_source_type": "Repository",
            "ruleset_source": "example/repo",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": "Required gate", "integration_id": 123},
                    {"context": "Tests / Required Gate", "integration_id": 123},
                    {"context": "swift-quality / Swift quality", "integration_id": 123},
                ],
                "do_not_enforce_on_create": False,
            },
        },
    ]


class EffectiveMainRulesAuditTests(unittest.TestCase):
    def test_accepts_desired_effective_main_policy(self) -> None:
        self.assertEqual([], validate_effective_main_rules(desired_rules()))

    def test_rejects_current_legacy_approval_deadlock(self) -> None:
        rules = [
            {"type": "deletion", "ruleset_id": 23140953},
            {"type": "non_fast_forward", "ruleset_id": 23140953},
            {
                "type": "pull_request",
                "ruleset_id": 23140953,
                "parameters": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                    "required_reviewers": [],
                    "require_extra_approval_for_unattributed_changes": True,
                },
            },
        ]

        errors = validate_effective_main_rules(rules)

        self.assertTrue(any("required_approving_review_count must equal 0" in error for error in errors))
        self.assertTrue(any("required_linear_history rule is required" in error for error in errors))
        self.assertTrue(any("required_status_checks rule is required" in error for error in errors))

    def test_rejects_overlapping_legacy_pull_request_rule(self) -> None:
        rules = desired_rules()
        rules.append(
            {
                "type": "pull_request",
                "ruleset_id": 23140953,
                "parameters": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                },
            }
        )

        errors = validate_effective_main_rules(rules)

        self.assertTrue(any("pull_request rule must appear exactly once" in error for error in errors))
        self.assertTrue(any("23140953" in error for error in errors))

    def test_rejects_required_check_drift(self) -> None:
        rules = desired_rules()
        status = next(rule for rule in rules if rule["type"] == "required_status_checks")
        status["parameters"]["required_status_checks"] = [
            {"context": "Required gate"},
            {"context": "renamed-swift-check"},
        ]

        errors = validate_effective_main_rules(rules)

        self.assertTrue(any("required check contexts must equal" in error for error in errors))

    def test_rejects_unexpected_effective_rule_type(self) -> None:
        rules = desired_rules()
        rules.append({"type": "update", "ruleset_id": 999})

        errors = validate_effective_main_rules(rules)

        self.assertTrue(any("unexpected effective main rule types" in error for error in errors))

    def test_rejects_malformed_payload(self) -> None:
        self.assertTrue(validate_effective_main_rules({"rules": []}))
        self.assertTrue(validate_effective_main_rules([{"ruleset_id": 1}]))

    def test_cli_accepts_gh_paginate_slurp_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = Path(temporary_directory) / "effective-rules.json"
            payload.write_text(
                json.dumps([desired_rules()]) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/ci/audit_effective_rules.py",
                    str(payload),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("match the Solo governance contract", result.stdout)

    def test_live_audit_wrapper_binds_repository_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            rules_file = root / "rules.json"
            rules_file.write_text(
                json.dumps(desired_rules()) + "\n",
                encoding="utf-8",
            )
            fake_gh.write_text(
                textwrap.dedent(
                    """\
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
                        print(json.dumps({
                            "id": repository_id,
                            "full_name": "example/repo",
                            "default_branch": default_branch,
                        }))
                        raise SystemExit(0)

                    if endpoint == "repos/example/repo/rules/branches/main?per_page=100":
                        rules = json.loads(Path(os.environ["GH_FAKE_RULES_FILE"]).read_text())
                        print(json.dumps([rules]))
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
                    env["GH_FAKE_RULES_FILE"] = str(rules_file)
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
                            "effective default-branch rules match",
                            result.stdout,
                        )
                    else:
                        self.assertNotEqual(0, result.returncode)
                        self.assertIn(
                            "Repository identity or default branch changed",
                            result.stderr,
                        )

    def test_live_audit_wrapper_rejects_effective_rules_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            rules_before = root / "rules-before.json"
            rules_after = root / "rules-after.json"
            count_file = root / "rules-count"

            rules_before.write_text(
                json.dumps(desired_rules()) + "\n",
                encoding="utf-8",
            )
            rules_after.write_text(
                json.dumps(
                    [
                        rule
                        for rule in desired_rules()
                        if rule.get("type") != "required_status_checks"
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            fake_gh.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import os
                    from pathlib import Path
                    import sys

                    endpoint = sys.argv[-1]
                    if endpoint == "repos/example/repo":
                        print(json.dumps({
                            "id": 101,
                            "full_name": "example/repo",
                            "default_branch": "main",
                        }))
                        raise SystemExit(0)

                    if endpoint == "repos/example/repo/rules/branches/main?per_page=100":
                        count_file = Path(os.environ["GH_FAKE_RULE_COUNT_FILE"])
                        count = int(count_file.read_text() or "0") if count_file.exists() else 0
                        count += 1
                        count_file.write_text(str(count))
                        rules_path = (
                            os.environ["GH_FAKE_RULES_BEFORE"]
                            if count == 1
                            else os.environ["GH_FAKE_RULES_AFTER"]
                        )
                        rules = json.loads(Path(rules_path).read_text())
                        print(json.dumps([rules]))
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
            env["GH_FAKE_RULE_COUNT_FILE"] = str(count_file)
            env["GH_FAKE_RULES_BEFORE"] = str(rules_before)
            env["GH_FAKE_RULES_AFTER"] = str(rules_after)
            result = subprocess.run(
                ["bash", str(LIVE_AUDIT), "example/repo"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            observed_read_count = count_file.read_text()

        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("required_status_checks rule is required", result.stderr)
        self.assertEqual("2", observed_read_count)

    def test_live_audit_wrapper_is_read_only_and_uses_effective_rules_endpoint(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        self.assertIn('rules/branches/', text)
        self.assertIn('--paginate', text)
        self.assertIn('--slurp', text)
        self.assertIn('audit_effective_rules.py', text)
        for mutation in (
            '--method POST',
            '--method PUT',
            '--method PATCH',
            '--method DELETE',
            'rulesets/',
        ):
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, text)

    def test_cli_reports_live_policy_drift(self) -> None:
        legacy = [
            {"type": "deletion", "ruleset_id": 23140953},
            {"type": "non_fast_forward", "ruleset_id": 23140953},
            {
                "type": "pull_request",
                "ruleset_id": 23140953,
                "parameters": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = Path(temporary_directory) / "legacy-rules.json"
            payload.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/ci/audit_effective_rules.py",
                    str(payload),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("required_approving_review_count must equal 0", result.stderr)
        self.assertIn("required_status_checks rule is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
