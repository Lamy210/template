import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/tests.yml"
EVALUATOR = ROOT / "scripts/test/evaluate-required-gate.py"


class RequiredGateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def policy_source(self):
        match = re.search(
            r"python3 - \"\$\{RUNNER_TEMP\}/required-gate-input\.json\" <<'PY'\n"
            r"(?P<source>.*?)\n\s+PY\n",
            self.workflow,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "required-gate normalized policy heredoc not found")
        return textwrap.dedent(match.group("source"))

    def test_required_gate_receives_classifier_job_result(self):
        self.assertIn(
            "CLASSIFY_RESULT: ${{ needs.classify.result }}",
            self.workflow,
        )

    def test_classifier_infrastructure_failure_is_fail_closed(self):
        env = os.environ.copy()
        env.update(
            {
                "CLASSIFY_RESULT": "failure",
                "CONFIGURED": "",
                "CONFIGURATION_ERROR": "",
                "UNIT_RESULT": "skipped",
                "INTEGRATION_ENABLED": "",
                "INTEGRATION_REQUIRED": "",
                "INTEGRATION_RESULT": "skipped",
                "E2E_ENABLED": "",
                "E2E_REQUIRED": "",
                "E2E_RESULT": "skipped",
                "VISUAL_ENABLED": "",
                "VISUAL_REQUIRED": "",
                "VISUAL_RESULT": "skipped",
                "COVERAGE_ENABLED": "",
                "COVERAGE_REQUIRED": "",
                "COVERAGE_RESULT": "skipped",
            }
        )

        with tempfile.TemporaryDirectory() as temporary:
            policy_path = Path(temporary) / "policy.json"
            built = subprocess.run(
                ["python3", "-", str(policy_path)],
                input=self.policy_source(),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(built.returncode, 0, built.stderr)

            evaluated = subprocess.run(
                ["python3", str(EVALUATOR), "--input", str(policy_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(
                evaluated.returncode,
                0,
                "classifier infrastructure failure must not become not-configured/pass",
            )
            self.assertIn("configuration-error", evaluated.stdout)


if __name__ == "__main__":
    unittest.main()
