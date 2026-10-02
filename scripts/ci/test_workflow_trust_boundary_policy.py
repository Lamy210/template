from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.workflow_trust_boundary_policy import (
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]


class WorkflowTrustBoundaryPolicyTests(unittest.TestCase):
    def validate(self, body: str, path: str = ".github/workflows/fixture.yml"):
        return validate_workflow_text(Path(path), body)

    def test_rejects_pull_request_target(self) -> None:
        for trigger in (
            "on:\n  pull_request_target:",
            "on: pull_request_target",
            "on: [push, pull_request_target]",
            '"on": [pull_request, pull_request_target]',
        ):
            with self.subTest(trigger=trigger):
                violations = self.validate(
                    f"""
{trigger}
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
"""
                )
                self.assertEqual(1, len(violations))
                self.assertIn("pull_request_target", violations[0].message)

    def test_rejects_encoded_inline_pull_request_target(self) -> None:
        for trigger in (
            r'on: "pull_request_\u0074arget"',
            r'on: [push, "pull_request_\u0074arget"]',
            r'on: !!str pull_request_target',
        ):
            with self.subTest(trigger=trigger):
                violations = self.validate(
                    f"""
{trigger}
permissions: {{}}
jobs:
  test:
    runs-on: ubuntu-latest
"""
                )
                self.assertEqual(1, len(violations), violations)
                self.assertIn("inline workflow triggers", violations[0].message)

    def test_rejects_block_scalar_and_multiline_flow_triggers(self) -> None:
        for trigger in (
            """
on: >-
  pull_request_target
""",
            """
on: [
  push,
  pull_request_target
]
""",
        ):
            with self.subTest(trigger=trigger):
                violations = self.validate(
                    f"""
{trigger}
permissions: {{}}
jobs:
  test:
    runs-on: ubuntu-latest
"""
                )
                self.assertEqual(1, len(violations), violations)
                self.assertIn("inline workflow triggers", violations[0].message)

    def test_accepts_canonical_inline_trigger_literals(self) -> None:
        for trigger in (
            "on: push",
            'on: "push"',
            "on: 'workflow_dispatch'",
            "on: [push, pull_request]",
            'on: ["push", \\'workflow_dispatch\\']',
        ):
            with self.subTest(trigger=trigger):
                violations = self.validate(
                    f"""
{trigger}
permissions: {{}}
jobs:
  test:
    runs-on: ubuntu-latest
"""
                )
                self.assertEqual([], violations)

    def test_rejects_deeply_indented_pull_request_target(self) -> None:
        violations = self.validate(
            """
on:
    pull_request_target:
permissions: {}
jobs:
    test:
        runs-on: ubuntu-latest
"""
        )
        self.assertEqual(1, len(violations), violations)
        self.assertIn("pull_request_target", violations[0].message)

    def test_rejects_encoded_or_block_scalar_secrets_inherit(self) -> None:
        for body in (
            r"""
on:
  workflow_dispatch:
permissions: {}
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    secrets: "inhe\u0072it"
""",
            """
on:
  workflow_dispatch:
permissions: {}
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    secrets: >-
      inherit
""",
        ):
            with self.subTest(body=body):
                violations = self.validate(body)
                self.assertEqual(1, len(violations), violations)
                self.assertEqual("job:call", violations[0].scope)
                self.assertIn("secrets scalar forms", violations[0].message)

    def test_accepts_named_secret_mapping_and_empty_mapping(self) -> None:
        for secrets in (
            """secrets:
      token: ${{ secrets.TOKEN }}""",
            "secrets: {}",
        ):
            with self.subTest(secrets=secrets):
                violations = self.validate(
                    f"""
on:
  workflow_dispatch:
permissions: {{}}
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    {secrets}
"""
                )
                self.assertEqual([], violations)

    def test_rejects_secrets_inherit(self) -> None:
        for value in ("inherit", '"inherit"', "'inherit'"):
            with self.subTest(value=value):
                violations = self.validate(
                    f"""
on:
  workflow_dispatch:
permissions:
  contents: read
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    secrets: {value}
"""
                )
                self.assertEqual(1, len(violations))
                self.assertIn("secrets: inherit", violations[0].message)

    def test_rejects_any_unapproved_environment(self) -> None:
        violations = self.validate(
            """
on:
  push:
permissions:
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("Environment usage is forbidden", violations[0].message)

    def test_deeply_indented_environment_keeps_job_scope(self) -> None:
        violations = self.validate(
            """
on:
    push:
permissions: {}
jobs:
    deploy:
        runs-on: ubuntu-latest
        environment: production
"""
        )
        self.assertEqual(1, len(violations), violations)
        self.assertEqual("job:deploy", violations[0].scope)
        self.assertIn("Environment usage is forbidden", violations[0].message)

    def test_accepts_exact_privileged_release_environment(self) -> None:
        violations = self.validate(
            """
on:
  workflow_call:
permissions: {}
jobs:
  release:
    runs-on: macos-latest
    environment: release
""",
            path=".github/workflows/reusable-macos-release.yml",
        )
        self.assertEqual([], violations)

    def test_top_level_environment_after_jobs_does_not_satisfy_release_job(self) -> None:
        violations = self.validate(
            """
on:
  workflow_call:
permissions: {}
jobs:
  release:
    runs-on: macos-latest
environment: release
""",
            path=".github/workflows/reusable-macos-release.yml",
        )
        self.assertEqual(2, len(violations), violations)
        self.assertTrue(
            any(
                item.scope == "workflow"
                and "Environment usage is forbidden" in item.message
                for item in violations
            ),
            violations,
        )
        self.assertTrue(
            any(
                item.scope == "job:release"
                and "required release-boundary Environment" in item.message
                for item in violations
            ),
            violations,
        )

    def test_rejects_expression_or_renamed_release_environment(self) -> None:
        for value in (
            "production",
            "${{ inputs.environment }}",
            "",
        ):
            with self.subTest(value=value):
                violations = self.validate(
                    f"""
on:
  workflow_call:
permissions: {{}}
jobs:
  release:
    runs-on: macos-latest
    environment: {value}
""",
                    path=".github/workflows/reusable-macos-release.yml",
                )
                self.assertTrue(violations)
                self.assertTrue(
                    any(
                        "must be literal" in item.message
                        or "missing" in item.message
                        for item in violations
                    ),
                    violations,
                )

    def test_accepts_disposable_release_environment_proof(self) -> None:
        violations = self.validate(
            """
on:
  workflow_dispatch:
permissions: {}
jobs:
  baseline:
    runs-on: ubuntu-latest
  environment-probe:
    runs-on: ubuntu-latest
    environment: release
""",
            path="examples/release-environment-proof.yml",
        )
        self.assertEqual([], violations)

    def test_rejects_release_environment_on_wrong_job(self) -> None:
        violations = self.validate(
            """
on:
  workflow_call:
permissions: {}
jobs:
  other:
    runs-on: ubuntu-latest
    environment: release
  release:
    runs-on: macos-latest
""",
            path=".github/workflows/reusable-macos-release.yml",
        )
        self.assertEqual(2, len(violations))
        self.assertTrue(
            any("Environment usage is forbidden" in item.message for item in violations),
            violations,
        )
        self.assertTrue(
            any("required release-boundary Environment" in item.message for item in violations),
            violations,
        )

    def test_quoted_keys_cannot_bypass_trust_boundaries(self) -> None:
        trigger = self.validate(
            """
on:
  "pull_request_target":
permissions: {}
jobs:
  test:
    runs-on: ubuntu-latest
"""
        )
        self.assertTrue(any("pull_request_target" in item.message for item in trigger))

        secrets = self.validate(
            """
on:
  workflow_dispatch:
permissions: {}
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
    "secrets": inherit
"""
        )
        self.assertTrue(any("secrets: inherit" in item.message for item in secrets))

        environment = self.validate(
            """
on:
  push:
permissions: {}
"jobs":
  "deploy":
    runs-on: ubuntu-latest
    "environment": production
"""
        )
        self.assertTrue(
            any("Environment usage is forbidden" in item.message for item in environment),
            environment,
        )

    def test_repository_workflows_follow_trust_boundary_policy(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
