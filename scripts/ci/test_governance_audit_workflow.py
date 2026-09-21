from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/governance-audit.yml"


class GovernanceAuditWorkflowContractTests(unittest.TestCase):
    def test_workflow_exists_and_is_manual_only(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("schedule:", text)

    def test_workflow_is_read_only(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("actions: write", text)
        self.assertNotIn("pull-requests: write", text)
        self.assertNotIn("administration: write", text)

    def test_workflow_runs_effective_rules_doctor_for_current_repository(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("bash scripts/ci/audit-live-main-rules.sh", text)
        self.assertIn("${{ github.repository }}", text)
        self.assertIn("GH_TOKEN: ${{ github.token }}", text)

    def test_workflow_runs_release_tag_ruleset_doctor_for_current_repository(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("bash scripts/ci/audit-live-release-tag-ruleset.sh", text)
        self.assertIn("${{ github.repository }}", text)

    def test_checkout_does_not_persist_credentials(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("persist-credentials: false", text)


if __name__ == "__main__":
    unittest.main()
