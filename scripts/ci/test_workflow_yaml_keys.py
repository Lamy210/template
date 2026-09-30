from __future__ import annotations

import re
import unittest

from scripts.ci.workflow_yaml_keys import (
    YAML_KEY_TOKEN,
    normalize_yaml_key,
    yaml_key_pattern,
)


class WorkflowYamlKeyTests(unittest.TestCase):
    def test_fixed_key_pattern_accepts_plain_and_quoted_keys(self) -> None:
        pattern = re.compile(rf"^{yaml_key_pattern('uses')}:$")
        for value in ("uses:", '"uses":', "'uses':"):
            with self.subTest(value=value):
                self.assertIsNotNone(pattern.fullmatch(value))

    def test_generic_key_token_accepts_supported_key_forms(self) -> None:
        pattern = re.compile(rf"^(?P<key>{YAML_KEY_TOKEN}):$")
        for value, expected in (
            ("contents:", "contents"),
            ('"contents":', "contents"),
            ("'contents':", "contents"),
        ):
            with self.subTest(value=value):
                match = pattern.fullmatch(value)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(expected, normalize_yaml_key(match.group("key")))

    def test_normalize_yaml_key_does_not_modify_plain_key(self) -> None:
        self.assertEqual("pull_request_target", normalize_yaml_key("pull_request_target"))


if __name__ == "__main__":
    unittest.main()
