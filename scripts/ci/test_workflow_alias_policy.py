from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.workflow_alias_policy import (
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class WorkflowAliasPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path(".github/workflows/fixture.yml"), body)

    def test_rejects_mapping_anchor_and_job_alias(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  base: &base_job
    runs-on: ubuntu-latest
    steps:
      - run: echo ok
  copy: *base_job
"""
        )
        self.assertEqual(["&base_job", "*base_job"], [item.token for item in violations])

    def test_rejects_scalar_alias_in_run(self) -> None:
        violations = self.validate(
            """
command: &command echo unsafe
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: *command
"""
        )
        self.assertEqual(2, len(violations))
        self.assertTrue(any(item.token == "*command" for item in violations))

    def test_rejects_alias_in_security_sensitive_mapping(self) -> None:
        violations = self.validate(
            """
shared: &shared
  contents: write
jobs:
  test:
    runs-on: ubuntu-latest
    permissions: *shared
"""
        )
        self.assertEqual(["&shared", "*shared"], [item.token for item in violations])

    def test_accepts_anchor_like_text_inside_quotes(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      LITERAL_ONE: "*alias"
      LITERAL_TWO: '&anchor'
"""
        )
        self.assertEqual([], violations)

    def test_accepts_shell_globs_and_background_tokens_in_run_blocks(self) -> None:
        violations = self.validate(
            """
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo *swift && echo done
      - run: |
          find . -name '*.swift'
          first &
          wait
"""
        )
        self.assertEqual([], violations)

    def test_repository_workflows_do_not_use_yaml_anchors_or_aliases(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
