from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.workflow_permission_policy import (
    parse_permission_blocks,
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class WorkflowPermissionPolicyTests(unittest.TestCase):
    def validate(self, body: str, path: str = ".github/workflows/fixture.yml"):
        return validate_workflow_text(Path(path), body)

    def test_requires_explicit_top_level_permissions(self) -> None:
        violations = self.validate(
            """
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("top-level permissions", violations[0].message)

    def test_accepts_read_only_or_empty_top_level_permissions(self) -> None:
        for permissions in (
            "permissions: {}",
            "permissions:\n  contents: read",
            "permissions:\n  contents: read\n  actions: read",
            "permissions:\n  contents: none",
        ):
            with self.subTest(permissions=permissions):
                violations = self.validate(
                    f"""
on:
  push:
{permissions}
jobs:
  test:
    runs-on: ubuntu-latest
"""
                )
                self.assertEqual([], violations)

    def test_rejects_top_level_write_and_shortcuts(self) -> None:
        for permissions in (
            "permissions:\n  contents: write",
            "permissions: write-all",
            "permissions: read-all",
            "permissions: ${{ inputs.permissions }}",
        ):
            with self.subTest(permissions=permissions):
                violations = self.validate(
                    f"""
on:
  push:
{permissions}
jobs:
  test:
    runs-on: ubuntu-latest
"""
                )
                self.assertTrue(violations)
                self.assertTrue(
                    any(
                        "top-level permissions" in item.message
                        or "read/none" in item.message
                        for item in violations
                    ),
                    violations,
                )

    def test_accepts_explicit_none_at_job_scope(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: none
"""
        )
        self.assertEqual([], violations)

    def test_rejects_job_write_outside_release_allowlist(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: write
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("write permissions are forbidden", violations[0].message)

    def test_accepts_exact_release_publication_write_permission(self) -> None:
        violations = self.validate(
            """
on:
  workflow_call:
permissions: {}
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: write
""",
            path=".github/workflows/reusable-macos-release.yml",
        )
        self.assertEqual([], violations)

    def test_rejects_broadened_release_publication_permission(self) -> None:
        violations = self.validate(
            """
on:
  workflow_call:
permissions: {}
jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      actions: read
      contents: write
      pull-requests: write
""",
            path=".github/workflows/reusable-macos-release.yml",
        )
        self.assertTrue(violations)
        self.assertTrue(
            any("must equal" in item.message for item in violations),
            violations,
        )

    def test_rejects_missing_allowlisted_publish_job_permissions(self) -> None:
        violations = self.validate(
            """
on:
  workflow_call:
permissions: {}
jobs:
  publish:
    runs-on: ubuntu-latest
""",
            path=".github/workflows/reusable-macos-release.yml",
        )
        self.assertEqual(1, len(violations))
        self.assertIn("allowlist target is missing", violations[0].message)

    def test_parser_distinguishes_workflow_and_job_permissions(self) -> None:
        blocks = parse_permission_blocks(
            Path(".github/workflows/fixture.yml"),
            """
on:
  push:
permissions:
  contents: read
jobs:
  one:
    permissions:
      contents: read
    runs-on: ubuntu-latest
  two:
    permissions: {}
    runs-on: ubuntu-latest
""",
        )
        self.assertEqual(
            ["workflow", "job:one", "job:two"],
            [item.scope for item in blocks],
        )
        self.assertEqual({"contents": "read"}, blocks[0].values)
        self.assertEqual({}, blocks[2].values)
        self.assertEqual("{}", blocks[2].inline)

    def test_repository_workflows_follow_permission_policy(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
