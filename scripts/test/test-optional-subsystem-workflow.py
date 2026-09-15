#!/usr/bin/env python3
"""Contract tests for optional test subsystem result propagation."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
EVALUATOR = ROOT / "scripts" / "test" / "evaluate-required-gate.py"


class OptionalSubsystemWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tests = (WORKFLOWS / "tests.yml").read_text(encoding="utf-8")
        cls.swift = (WORKFLOWS / "reusable-swift-tests.yml").read_text(encoding="utf-8")
        cls.e2e = (WORKFLOWS / "reusable-macos-e2e.yml").read_text(encoding="utf-8")
        cls.visual = (WORKFLOWS / "reusable-visual-regression.yml").read_text(encoding="utf-8")

    def test_required_gate_already_treats_optional_failure_as_warning(self) -> None:
        payload = """{
          "schemaVersion": 1,
          "subsystems": {
            "Unit": {"status": "success", "required": true, "classification": "applicable"},
            "Integration": {"status": "failure", "required": false, "classification": "applicable"},
            "E2E": {"status": "disabled", "required": false, "classification": "not-applicable"},
            "Visual": {"status": "disabled", "required": false, "classification": "not-applicable"},
            "Coverage": {"status": "disabled", "required": false, "classification": "not-applicable"}
          }
        }\n"""
        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary) / "policy.json"
            policy.write_text(payload, encoding="utf-8")
            completed = subprocess.run(
                ["python3", str(EVALUATOR), "--input", str(policy)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("optional subsystem failed", completed.stdout)

    def test_swift_reusable_exposes_raw_test_and_coverage_results(self) -> None:
        self.assertIn("test_result:", self.swift)
        self.assertIn("coverage_result:", self.swift)
        self.assertIn("required:", self.swift)
        self.assertIn("coverage_required:", self.swift)
        self.assertIn("value: ${{ jobs.tests.outputs.test_result }}", self.swift)
        self.assertIn("value: ${{ jobs.tests.outputs.coverage_result }}", self.swift)

    def test_e2e_reusable_exposes_raw_result_and_requiredness(self) -> None:
        self.assertIn("required:\n", self.e2e)
        self.assertIn("result:\n", self.e2e)
        self.assertIn("value: ${{ jobs.e2e.outputs.result }}", self.e2e)

    def test_visual_reusable_exposes_raw_result_and_requiredness(self) -> None:
        self.assertIn("required:\n", self.visual)
        self.assertIn("result:\n", self.visual)
        self.assertIn("value: ${{ jobs.visual.outputs.result }}", self.visual)

    def test_callers_forward_required_policy_to_reusable_workflows(self) -> None:
        self.assertIn("required: true", self.tests)
        self.assertIn(
            "coverage_required: ${{ needs.classify.outputs.coverage_required == 'true' }}",
            self.tests,
        )
        self.assertIn(
            "required: ${{ needs.classify.outputs.integration_required == 'true' }}",
            self.tests,
        )
        self.assertIn(
            "required: ${{ needs.classify.outputs.e2e_required == 'true' }}",
            self.tests,
        )
        self.assertIn(
            "required: ${{ needs.classify.outputs.visual_required == 'true' }}",
            self.tests,
        )

    def test_visual_execution_and_publication_require_raw_e2e_visual_success(self) -> None:
        self.assertIn(
            "needs.e2e-run.outputs.result == 'success'",
            self.tests,
        )
        self.assertIn(
            "needs.visual-run.outputs.result == 'success'",
            self.tests,
        )

    def test_proxy_jobs_publish_raw_results_for_required_gate(self) -> None:
        for expression in (
            "needs.unit.outputs.result",
            "needs.integration.outputs.result",
            "needs.e2e.outputs.result",
            "needs.visual.outputs.result",
            "needs.coverage.outputs.result",
        ):
            self.assertIn(expression, self.tests)

        for expression in (
            "needs.unit-run.outputs.test_result",
            "needs.integration-run.outputs.test_result",
            "needs.e2e-run.outputs.result",
            "needs.visual-run.outputs.result",
            "needs.unit-run.outputs.coverage_result",
        ):
            self.assertIn(expression, self.tests)


if __name__ == "__main__":
    unittest.main()
