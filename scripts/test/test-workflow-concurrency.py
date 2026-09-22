from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]

WORKFLOWS = {
    "quality": REPO_ROOT / ".github/workflows/quality.yml",
    "swift-quality": REPO_ROOT / ".github/workflows/swift-quality.yml",
    "tests": REPO_ROOT / ".github/workflows/tests.yml",
    "test-infrastructure": REPO_ROOT / ".github/workflows/test-infrastructure.yml",
    "optional-subsystem-runtime-tests": REPO_ROOT
    / ".github/workflows/optional-subsystem-runtime-tests.yml",
    "visual-bundle-tests": REPO_ROOT / ".github/workflows/visual-bundle-tests.yml",
}


class WorkflowConcurrencyTests(unittest.TestCase):
    def test_pr_workflows_cancel_only_stale_pull_request_runs(self) -> None:
        for name, path in WORKFLOWS.items():
            with self.subTest(workflow=name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("concurrency:\n", text)
                self.assertIn(
                    "${{ github.event.pull_request.number || github.ref }}",
                    text,
                )
                self.assertIn(
                    "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
                    text,
                )

    def test_concurrency_group_is_scoped_by_workflow(self) -> None:
        for name, path in WORKFLOWS.items():
            with self.subTest(workflow=name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("group: ", text)
                self.assertIn("${{ github.workflow }}", text)


if __name__ == "__main__":
    unittest.main()
