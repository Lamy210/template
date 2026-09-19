from __future__ import annotations

import unittest

from scripts.ci.audit_effective_rules import validate_effective_main_rules


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


if __name__ == "__main__":
    unittest.main()
