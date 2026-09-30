from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.workflow_flow_mapping_policy import (
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class WorkflowFlowMappingPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path(".github/workflows/fixture.yml"), body)

    def test_rejects_inline_permissions_mapping(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: { contents: write }
jobs:
  test:
    runs-on: ubuntu-latest
"""
        )
        self.assertEqual(1, len(violations))

    def test_rejects_flow_mapping_step(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - { uses: owner/action@v4 }
"""
        )
        self.assertEqual(1, len(violations))

    def test_rejects_flow_mapping_nested_in_sequence(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps: [{ run: echo unsafe }]
"""
        )
        self.assertEqual(1, len(violations))

    def test_rejects_multiline_flow_mapping_start(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        with: {
          persist-credentials: true
        }
"""
        )
        self.assertEqual(1, len(violations))

    def test_accepts_explicit_empty_mapping(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    permissions: { }
    runs-on: ubuntu-latest
"""
        )
        self.assertEqual([], violations)

    def test_accepts_flow_sequences(self) -> None:
        violations = self.validate(
            """
on: [push, pull_request]
permissions: {}
jobs:
  test:
    needs: [build, lint]
    runs-on: ubuntu-latest
"""
        )
        self.assertEqual([], violations)

    def test_accepts_github_expressions_with_braces(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    if: ${{ always() && github.repository != '' }}
    runs-on: ubuntu-latest
"""
        )
        self.assertEqual([], violations)

    def test_accepts_quoted_flow_mapping_text(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      EXAMPLE: "{ key: value }"
"""
        )
        self.assertEqual([], violations)

    def test_accepts_mapping_text_inside_run_block(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python3 - <<'PY'
          payload = {
              "key": "value",
          }
          print(payload)
          PY
"""
        )
        self.assertEqual([], violations)

    def test_repository_workflows_use_block_mappings(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
