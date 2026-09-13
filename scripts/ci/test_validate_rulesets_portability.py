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

    def test_rejects_required_check_integration_id(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["required_status_checks"][0]["integration_id"] = 15368

        errors = validate_main_solo(document)

        self.assertTrue(any("required checks must contain only context" in error for error in errors))

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


class PortableReleaseTagRulesetTests(unittest.TestCase):
    def test_rejects_creation_rule_that_blocks_new_release_tags(self) -> None:
        document = copy.deepcopy(valid_release_tags())
        document["rules"].append({"type": "creation"})

        errors = validate_release_tags(document)

        self.assertTrue(any("unexpected release tag rule types" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
