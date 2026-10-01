from __future__ import annotations

from pathlib import Path
import unittest

from scripts.ci.actions_supply_chain_policy import (
    parse_action_uses,
    validate_repository,
    validate_workflow_text,
)


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


class ActionsSupplyChainPolicyTests(unittest.TestCase):
    def validate(self, body: str):
        return validate_workflow_text(Path("fixture.yml"), body)

    def test_accepts_sha_pinned_external_action(self) -> None:
        violations = self.validate(
            f"""
jobs:
  test:
    steps:
      - name: External
        uses: owner/action@{SHA}
"""
        )
        self.assertEqual([], violations)

    def test_accepts_sha_pinned_action_subpath(self) -> None:
        violations = self.validate(
            f"""
jobs:
  test:
    steps:
      - uses: owner/repo/sub/action@{SHA}
"""
        )
        self.assertEqual([], violations)

    def test_accepts_local_actions_in_steps(self) -> None:
        for value in (
            "./.github/actions/local-action",
            "$/.github/actions/local-action",
        ):
            with self.subTest(value=value):
                body = f"""
jobs:
  test:
    steps:
      - uses: {value}
"""
                self.assertEqual([], self.validate(body))
                uses = parse_action_uses(Path("fixture.yml"), body)
                self.assertEqual("step", uses[0].scope)

    def test_accepts_local_reusable_workflows(self) -> None:
        for value in (
            "./.github/workflows/reusable.yml",
            "$/.github/workflows/reusable.yml",
        ):
            with self.subTest(value=value):
                body = f"""
jobs:
  reusable:
    uses: {value}
"""
                self.assertEqual([], self.validate(body))
                uses = parse_action_uses(Path("fixture.yml"), body)
                self.assertEqual("job", uses[0].scope)

    def test_rejects_invalid_job_level_local_uses(self) -> None:
        for value in (
            "./.github/actions/local-action",
            "$/.github/actions/local-action",
            "./scripts/reusable.yml",
            "$/.github/workflows/nested/reusable.yml",
            "$/.github/workflows/reusable.yml@main",
        ):
            with self.subTest(value=value):
                violations = self.validate(
                    f"""
jobs:
  reusable:
    uses: {value}
"""
                )
                self.assertEqual(1, len(violations), violations)
                self.assertIn(
                    "job-level local uses must reference a reusable workflow",
                    violations[0].message,
                )

    def test_rejects_mutable_external_refs(self) -> None:
        for ref in ("v4", "main", "release", "A" * 40, "a" * 39):
            with self.subTest(ref=ref):
                violations = self.validate(
                    f"""
jobs:
  test:
    steps:
      - uses: owner/action@{ref}
"""
                )
                self.assertEqual(1, len(violations))
                self.assertIn("full lowercase commit SHA", violations[0].message)

    def test_checkout_requires_persist_credentials_false(self) -> None:
        for with_block in (
            "",
            "        with:\n          fetch-depth: 0\n",
            "        with:\n          persist-credentials: true\n",
            "        with:\n          persist-credentials: ${{ inputs.persist }}\n",
        ):
            with self.subTest(with_block=with_block):
                violations = self.validate(
                    f"""
jobs:
  test:
    steps:
      - name: Checkout
        uses: actions/checkout@{SHA}
{with_block}"""
                )
                self.assertEqual(1, len(violations))
                self.assertIn("persist-credentials: false", violations[0].message)

    def test_compact_checkout_does_not_borrow_later_step_inputs(self) -> None:
        violations = self.validate(
            f"""
jobs:
  test:
    steps:
      - uses: actions/checkout@{SHA}
      - uses: owner/action@{SHA}
        with:
          persist-credentials: false
"""
        )
        self.assertEqual(1, len(violations))
        self.assertIn("persist-credentials: false", violations[0].message)

    def test_checkout_does_not_borrow_later_job_inputs(self) -> None:
        body = f"""
jobs:
  checkout-job:
    steps:
      - uses: actions/checkout@{SHA}
  reusable-job:
    uses: ./.github/workflows/reusable.yml
    with:
      persist-credentials: false
"""
        violations = self.validate(body)
        self.assertEqual(1, len(violations))
        self.assertIn("persist-credentials: false", violations[0].message)

        uses = parse_action_uses(Path("fixture.yml"), body)
        self.assertEqual({}, uses[0].with_values)

    def test_compact_checkout_accepts_its_own_with_block(self) -> None:
        violations = self.validate(
            f"""
jobs:
  test:
    steps:
      - uses: actions/checkout@{SHA}
        with:
          persist-credentials: false
      - uses: owner/action@{SHA}
        with:
          persist-credentials: true
"""
        )
        self.assertEqual([], violations)

    def test_compact_step_parser_keeps_with_values_isolated(self) -> None:
        uses = parse_action_uses(
            Path("fixture.yml"),
            f"""
jobs:
  test:
    steps:
      - uses: actions/checkout@{SHA}
      - uses: owner/action@{SHA}
        with:
          persist-credentials: false
""",
        )
        self.assertEqual({}, uses[0].with_values)
        self.assertEqual(
            {"persist-credentials": "false"},
            uses[1].with_values,
        )

    def test_checkout_accepts_quoted_false_and_inline_action_comment(self) -> None:
        violations = self.validate(
            f"""
jobs:
  test:
    steps:
      - name: Checkout
        uses: "actions/checkout@{SHA}" # pinned
        with:
          persist-credentials: "false"
"""
        )
        self.assertEqual([], violations)

    def test_parser_keeps_external_and_local_uses_separate(self) -> None:
        uses = parse_action_uses(
            Path("fixture.yml"),
            f"""
jobs:
  one:
    steps:
      - name: One
        uses: owner/action@{SHA}
  two:
    uses: ./.github/workflows/two.yml
""",
        )
        self.assertEqual(
            [f"owner/action@{SHA}", "./.github/workflows/two.yml"],
            [item.value for item in uses],
        )
        self.assertEqual(["step", "job"], [item.scope for item in uses])

    def test_quoted_keys_cannot_bypass_action_policy(self) -> None:
        mutable = self.validate(
            f"""
jobs:
  test:
    steps:
      - "uses": owner/action@v4
"""
        )
        self.assertEqual(1, len(mutable))
        self.assertIn("full lowercase commit SHA", mutable[0].message)

        checkout = self.validate(
            f"""
jobs:
  test:
    steps:
      - "uses": actions/checkout@{SHA}
        "with":
          "persist-credentials": true
"""
        )
        self.assertEqual(1, len(checkout))
        self.assertIn("persist-credentials: false", checkout[0].message)

    def test_repository_actions_follow_supply_chain_policy(self) -> None:
        violations = validate_repository(ROOT)
        self.assertEqual([], violations, violations)


if __name__ == "__main__":
    unittest.main()
