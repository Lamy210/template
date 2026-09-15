import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS_WORKFLOW = ROOT / ".github/workflows/tests.yml"
REUSABLE_VISUAL = ROOT / ".github/workflows/reusable-visual-regression.yml"


class VisualScheduleWiringTests(unittest.TestCase):
    def setUp(self):
        self.tests_workflow = TESTS_WORKFLOW.read_text(encoding="utf-8")
        self.reusable_visual = REUSABLE_VISUAL.read_text(encoding="utf-8")

    def test_tests_workflow_has_weekly_schedule(self):
        self.assertRegex(
            self.tests_workflow,
            re.compile(r"(?m)^  schedule:\n    - cron: ['\"]17 3 \* \* 0['\"]$"),
        )

    def test_visual_caller_explicitly_trusts_push_and_schedule(self):
        self.assertIn("trusted_events: push,schedule", self.tests_workflow)

    def test_scheduled_main_run_may_publish_after_required_gate(self):
        marker = "  publish-visual-baseline:\n"
        self.assertIn(marker, self.tests_workflow)
        publication = self.tests_workflow.split(marker, 1)[1]
        condition = next(
            line.strip()
            for line in publication.splitlines()
            if line.lstrip().startswith("if: ${{")
        )
        self.assertIn("github.ref == 'refs/heads/main'", condition)
        self.assertIn("github.event_name == 'push'", condition)
        self.assertIn("github.event_name == 'schedule'", condition)
        self.assertIn("needs.visual-run.result == 'success'", condition)
        self.assertIn("needs.required-gate.result == 'success'", condition)

    def test_reusable_visual_defaults_to_push_only_and_forwards_policy(self):
        self.assertRegex(
            self.reusable_visual,
            re.compile(
                r"(?ms)^      trusted_events:\n"
                r"        description: .*?\n"
                r"        required: false\n"
                r"        default: push\n"
                r"        type: string$"
            ),
        )
        self.assertIn("TRUSTED_EVENTS: ${{ inputs.trusted_events }}", self.reusable_visual)
        self.assertIn('--trusted-events "${TRUSTED_EVENTS}"', self.reusable_visual)
        self.assertIn('--expected-events "${TRUSTED_EVENTS}"', self.reusable_visual)


if __name__ == "__main__":
    unittest.main()
