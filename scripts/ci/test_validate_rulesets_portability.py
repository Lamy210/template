from __future__ import annotations

import copy
import unittest

from scripts.ci.test_validate_rulesets import valid_main_solo
from scripts.ci.validate_rulesets import validate_main_solo


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

    def test_rejects_required_check_integration_id(self) -> None:
        document = copy.deepcopy(valid_main_solo())
        status_rule = next(
            rule for rule in document["rules"] if rule["type"] == "required_status_checks"
        )
        status_rule["parameters"]["required_status_checks"][0]["integration_id"] = 15368

        errors = validate_main_solo(document)

        self.assertTrue(any("required checks must contain only context" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
