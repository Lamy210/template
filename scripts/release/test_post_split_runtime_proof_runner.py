from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/release/prove-post-split-ancestor-runtime.sh"


def run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


class PostSplitRuntimeProofRunnerTests(unittest.TestCase):
    def test_requires_explicit_disposable_confirmation(self) -> None:
        result = run_script(
            "--repository",
            "example/disposable",
            "--source-ref",
            "old-main",
            "--tag",
            "v0.0.1",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("--confirm-disposable", result.stderr)

    def test_refuses_current_repository(self) -> None:
        result = run_script(
            "--repository",
            "example/live",
            "--confirm-disposable",
            "example/live",
            "--source-ref",
            "old-main",
            "--tag",
            "v0.0.1",
            env={"GITHUB_REPOSITORY": "example/live"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the current repository", result.stderr)

    def test_rejects_noncanonical_stable_tag_before_github_access(self) -> None:
        result = run_script(
            "--repository",
            "example/disposable",
            "--confirm-disposable",
            "example/disposable",
            "--source-ref",
            "old-main",
            "--tag",
            "v01.0.0",
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("canonical stable SemVer", result.stderr)

    def test_rejects_existing_evidence_output_before_github_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "proof.json"
            output.write_text("{}\n", encoding="utf-8")
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                "--source-ref",
                "old-main",
                "--tag",
                "v0.0.1",
                "--evidence-output",
                str(output),
            )

        self.assertEqual(2, result.returncode)
        self.assertIn("must not already exist", result.stderr)

    def test_runner_contract_is_fail_closed_and_delegates_final_audit(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        for token in (
            "set -euo pipefail",
            "--confirm-disposable",
            "strict ancestor",
            "compare/",
            "contents/.github/workflows/",
            "release-build.yml",
            "release-publisher.yml",
            "snapshot_run_ids",
            "validated-release-input-",
            "actions/runs/",
            "audit-post-split-runtime-proof.sh",
            "audit_args",
            "--evidence-output",
            "refs/tags/",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

        self.assertIn("--method POST", text)
        self.assertNotIn("--method DELETE", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("post_split_proof_evidence.py", text)
        self.assertIn(
            'audit_args+=(--evidence-output "${evidence_output}")',
            text,
        )

    def test_runner_retains_proof_tag_as_audit_evidence(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("The stable tag is intentionally not deleted", text)
        self.assertNotIn("trap cleanup", text)
        self.assertNotIn("delete tag", text.lower())

    def test_source_run_waits_for_success_but_publisher_waits_only_for_validation(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('wait_for_run_completion "${source_run_id}" true', text)
        self.assertIn(
            'wait_for_publisher_validation_success "${publisher_run_id}"',
            text,
        )
        self.assertNotIn(
            'wait_for_run_completion "${publisher_run_id}" false',
            text,
        )
        self.assertIn(
            'attempts/${run_attempt}/jobs?per_page=100',
            text,
        )
        self.assertIn("Validate release input without secrets", text)
        self.assertIn('status == "completed"', text)
        self.assertIn('conclusion == "success"', text)
        self.assertIn("validator artifact", text)

    def test_publisher_discovery_paginates_validator_artifacts(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            '--paginate --slurp "repos/${repository}/actions/runs/${candidate_id}/artifacts?per_page=100"',
            text,
        )
        self.assertIn("publisher job pages disagree on total_count", text)
        self.assertIn(
            "publisher job pagination total_count does not match collected jobs",
            text,
        )


if __name__ == "__main__":
    unittest.main()
