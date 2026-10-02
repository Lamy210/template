from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.workflow_key_policy import (
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class WorkflowKeyPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path(".github/workflows/fixture.yml"), body)

    def test_accepts_plain_and_literal_quoted_keys(self) -> None:
        violations = self.validate(
            """
on:
  push:
"permissions": {}
'jobs':
  test:
    runs-on: ubuntu-latest
    steps:
      - "run": echo safe
"""
        )
        self.assertEqual([], violations)

    def test_rejects_escaped_security_sensitive_keys(self) -> None:
        for key in (
            r'"r\u0075n"',
            r'"u\u0073es"',
            r'"permissi\u006fns"',
            r'"environm\u0065nt"',
            r'"secr\u0065ts"',
        ):
            with self.subTest(key=key):
                violations = self.validate(
                    f"""
on:
  push:
permissions: {{}}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - {key}: echo unsafe
"""
                )
                self.assertEqual(1, len(violations), violations)
                self.assertEqual(key, violations[0].key)
                self.assertIn("YAML escapes", violations[0].message)

    def test_rejects_complex_single_quoted_key(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - 'r''un': echo unsafe
"""
        )
        self.assertEqual(1, len(violations), violations)

    def test_ignores_key_like_text_inside_run_block_and_comments(self) -> None:
        violations = self.validate(
            r"""
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      # "r\u0075n": not a mapping key
      - run: |
          "r\u0075n": shell text
          'r''un': shell text
"""
        )
        self.assertEqual([], violations)

    def test_repository_workflow_keys_are_canonical(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
