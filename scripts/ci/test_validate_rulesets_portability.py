from __future__ import annotations

import copy
import unittest

from scripts.ci.test_validate_rulesets import valid_main_solo, valid_release_tags
from scripts.ci.validate_rulesets import validate_main_solo, validate_release_tags


class PortableSoloRulesetTests(unittest.TestCase):
    def test_rejects_required_reviewers(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["required_reviewers"] = [
            {
                "file_patterns": ["**"],
                "minimum_approvals": 1,
                "reviewer": {"id": 123, "type": "Team"},
            }
        ]

        errors = validate_main_solo(document)

        self.assertTrue(any("required_reviewers must be empty or omitted" in error for error in errors))

    def test_rejects_extra_unattributed_change_approval(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["require_extra_approval_for_unattributed_changes"] = True

        errors = validate_main_solo(document)

        self.assertTrue(
            any(
                "require_extra_approval_for_unattributed_changes must be false or omitted" in error
                for error in errors
            )
        )

    def test_rejects_unknown_pull_request_parameter(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        pull_request = next(rule for rule in document["rules"] if rule["type"] == "pull_request")
        pull_request["parameters"]["future_approval_gate"] = True

        errors = validate_main_solo(document)

        self.assertTrue(any("unexpected pull_request parameters" in error for error in errors))

    def test_rejects_required_check_integration_id(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["required_status_checks"][0]["integration_id"] = 15368

        errors = validate_main_solo(document)

        self.assertTrue(any("required checks must contain only context" in error for error in errors))

    def test_rejects_non_string_required_check_context(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["required_status_checks"][0]["context"] = ["Required gate"]

        errors = validate_main_solo(document)

        self.assertTrue(any("required check contexts must be strings" in error for error in errors))

    def test_allows_explicit_status_checks_on_create(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["do_not_enforce_on_create"] = False

        errors = validate_main_solo(document)

        self.assertEqual([], errors)

    def test_rejects_skipping_status_checks_on_create(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["do_not_enforce_on_create"] = True

        errors = validate_main_solo(document)

        self.assertTrue(
            any("do_not_enforce_on_create must be false or omitted" in error for error in errors)
        )

    def test_rejects_unknown_status_rule_parameter(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["future_status_policy"] = True

        errors = validate_main_solo(document)

        self.assertTrue(any("unexpected required_status_checks parameters" in error for error in errors))

    def test_rejects_unexpected_main_rule_type(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["rules"].append(
            {
                "type": "update",
                "parameters": {"update_allows_fetch_and_merge": False},
            }
        )

        errors = validate_main_solo(document)

        self.assertTrue(any("unexpected main rule types" in error for error in errors))

    def test_rejects_metadata_on_simple_rule(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        deletion_rule = next(rule for rule in document["rules"] if rule["type"] == "deletion")
        deletion_rule["id"] = 123

        errors = validate_main_solo(document)

        self.assertTrue(any("deletion rule must contain only type" in error for error in errors))


class PortableReleaseTagRulesetTests(unittest.TestCase):
    def test_rejects_creation_rule_that_blocks_new_release_tags(self) -> None:
        document = copy.deepcopy(valid_release_tags())
        document["rules"].append({"type": "creation"})

        errors = validate_release_tags(document)

        self.assertTrue(any("unexpected release tag rule types" in error for error in errors))


class PortableRulesetStructureTests(unittest.TestCase):
    def test_rejects_missing_name(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document.pop("name")

        errors = validate_main_solo(document)

        self.assertTrue(any("name must be a non-empty string" in error for error in errors))

    def test_rejects_noncanonical_export_fields(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["source_type"] = "Repository"
        document["current_user_can_bypass"] = "never"

        errors = validate_main_solo(document)

        self.assertTrue(any("unexpected top-level fields" in error for error in errors))

    def test_rejects_extra_targeting_condition(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["conditions"]["repository_name"] = {
            "include": ["~ALL"],
            "exclude": [],
        }

        errors = validate_main_solo(document)

        self.assertTrue(any("conditions must contain only ref_name" in error for error in errors))

    def test_rejects_extra_ref_name_field(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["conditions"]["ref_name"]["future_selector"] = ["main"]

        errors = validate_main_solo(document)

        self.assertTrue(any("conditions.ref_name must contain only include and exclude" in error for error in errors))

    def test_rejects_malformed_rule_entry(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        document["rules"].append("deletion")

        errors = validate_main_solo(document)

        self.assertTrue(
            any("rules entries must be objects with string type" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
