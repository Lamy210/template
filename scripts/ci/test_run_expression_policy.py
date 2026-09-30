from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.run_expression_policy import (
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class RunExpressionPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path(".github/workflows/fixture.yml"), body)

    def test_rejects_expression_in_multiline_run_block(self) -> None:
        violations = self.validate(
            """
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Unsafe
        run: |
          echo "${{ github.event.pull_request.title }}"
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("route expression values through env", violations[0].message)

    def test_rejects_expression_in_inline_run_command(self) -> None:
        violations = self.validate(
            """
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.ref }}"
"""
        )
        self.assertEqual(1, len(violations))

    def test_rejects_expression_in_folded_run_block(self) -> None:
        violations = self.validate(
            """
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: >
          printf '%s\\n'
          "${{ inputs.value }}"
"""
        )
        self.assertEqual(1, len(violations))

    def test_accepts_expression_routed_through_env(self) -> None:
        violations = self.validate(
            """
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Safe
        env:
          EVENT_TITLE: ${{ github.event.pull_request.title }}
        run: |
          printf '%s\\n' "${EVENT_TITLE}"
"""
        )
        self.assertEqual([], violations)

    def test_accepts_expressions_outside_run_blocks(self) -> None:
        violations = self.validate(
            """
on:
  push:
jobs:
  test:
    if: ${{ always() }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@deadbeef
        with:
          ref: ${{ github.sha }}
"""
        )
        self.assertEqual([], violations)

    def test_repository_workflows_have_no_direct_run_expressions(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
