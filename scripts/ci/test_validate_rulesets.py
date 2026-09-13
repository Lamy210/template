from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.validate_rulesets import (
    validate_file,
    validate_main_solo,
    validate_release_tags,
)


def valid_main_solo() -> dict:
    return {
        "name": "Solo default branch",
        "target": "branch",
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
    }


def valid_release_tags() -> dict:
    return {
        "name": "Immutable release tags",
        "target": "tag",
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
    }


class MainSoloRulesetTests(unittest.TestCase):
    def test_valid_main_solo_has_no_errors(self) -> None:
        self.assertEqual([], validate_main_solo(valid_main_solo()))

    def test_rejects_required_approval(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["required_approving_review_count"] = 1

        errors = validate_main_solo(document)

        self.assertTrue(any("required_approving_review_count must equal 0" in error for error in errors))

    def test_rejects_release_branch_target(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["conditions"]["ref_name"]["include"].append("refs/heads/release-*")

        errors = validate_main_solo(document)

        self.assertTrue(any("ref_name.include must equal ['~DEFAULT_BRANCH']" in error for error in errors))

    def test_rejects_missing_or_extra_required_check_context(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["required_status_checks"] = [
            {"context": "Required gate"},
            {"context": "Unexpected check"},
        ]

        errors = validate_main_solo(document)

        self.assertTrue(any("required check contexts must equal" in error for error in errors))

    def test_rejects_duplicate_required_check_context(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["required_status_checks"] = [
            {"context": "Required gate"},
            {"context": "Required gate"},
        ]

        errors = validate_main_solo(document)

        self.assertTrue(any("required check contexts must equal" in error for error in errors))

    def test_rejects_disabled_strict_status_policy(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["strict_required_status_checks_policy"] = False

        errors = validate_main_solo(document)

        self.assertTrue(any("strict_required_status_checks_policy must be true" in error for error in errors))

    def test_rejects_disabled_review_thread_resolution(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["required_review_thread_resolution"] = False

        errors = validate_main_solo(document)

        self.assertTrue(any("required_review_thread_resolution must be true" in error for error in errors))

    def test_rejects_non_squash_merge_methods(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["allowed_merge_methods"] = ["merge", "squash", "rebase"]

        errors = validate_main_solo(document)

        self.assertTrue(any("allowed_merge_methods must equal ['squash']" in error for error in errors))

    def test_rejects_missing_linear_history_rule(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["rules"] = [
            rule for rule in document["rules"] if rule["type"] != "required_linear_history"
        ]

        errors = validate_main_solo(document)

        self.assertTrue(any("required_linear_history rule is required" in error for error in errors))

    def test_rejects_non_empty_bypass_actors(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["bypass_actors"] = [{"actor_id": 5, "actor_type": "RepositoryRole"}]

        errors = validate_main_solo(document)

        self.assertTrue(any("bypass_actors must be empty" in error for error in errors))

    def test_rejects_runtime_metadata(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["id"] = 123

        errors = validate_main_solo(document)

        self.assertTrue(any("runtime-only field 'id' is forbidden" in error for error in errors))

    def test_rejects_duplicate_singleton_rule_type(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        document["rules"].append(copy.deepcopy(pull_request))

        errors = validate_main_solo(document)

        self.assertTrue(any("pull_request rule must appear exactly once" in error for error in errors))


class ReleaseTagRulesetTests(unittest.TestCase):
    def test_valid_release_tags_has_no_errors(self) -> None:
        self.assertEqual([], validate_release_tags(valid_release_tags()))

    def test_rejects_missing_update_restriction(self) -> None:
        document = copy.deepcopy(valid_release_tags())
        document["rules"] = [rule for rule in document["rules"] if rule["type"] != "update"]

        errors = validate_release_tags(document)

        self.assertTrue(any("release tag update restriction is required" in error for error in errors))

    def test_rejects_missing_deletion_restriction(self) -> None:
        document = copy.deepcopy(valid_release_tags())
        document["rules"] = [rule for rule in document["rules"] if rule["type"] != "deletion"]

        errors = validate_release_tags(document)

        self.assertTrue(any("release tag deletion restriction is required" in error for error in errors))

    def test_rejects_branch_only_rules(self) -> None:
        document = copy.deepcopy(valid_release_tags())
        document["rules"].append(
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [{"context": "Required gate"}],
                },
            }
        )

        errors = validate_release_tags(document)

        self.assertTrue(any("required_status_checks is not allowed for release tags" in error for error in errors))

    def test_rejects_wrong_tag_target(self) -> None:
        document = copy.deepcopy(valid_release_tags())
        document["conditions"]["ref_name"]["include"] = ["refs/tags/release-*"]

        errors = validate_release_tags(document)

        self.assertTrue(any("ref_name.include must equal ['refs/tags/v*']" in error for error in errors))


class FileValidationTests(unittest.TestCase):
    def test_malformed_json_returns_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "ruleset.json"
            path.write_text("{not-json", encoding="utf-8")

            errors = validate_file(path, "main-solo")

        self.assertTrue(any("invalid JSON" in error for error in errors))

    def test_unknown_profile_returns_diagnostic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "ruleset.json"
            path.write_text(json.dumps(valid_main_solo()), encoding="utf-8")

            errors = validate_file(path, "unknown")

        self.assertTrue(any("unknown profile" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
