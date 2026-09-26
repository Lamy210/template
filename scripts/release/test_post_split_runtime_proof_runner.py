from __future__ import annotations

import os
from pathlib import Path
import subprocess
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
            "refs/tags/",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)

        self.assertIn("--method POST", text)
        self.assertNotIn("--method DELETE", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("secrets.", text)

    def test_runner_retains_proof_tag_as_audit_evidence(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("The stable tag is intentionally not deleted", text)
        self.assertNotIn("trap cleanup", text)
        self.assertNotIn("delete tag", text.lower())

    def test_source_run_must_complete_successfully_but_publisher_may_fail_later(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('wait_for_run_completion "${source_run_id}" true', text)
        self.assertIn('wait_for_run_completion "${publisher_run_id}" false', text)
        self.assertIn("validator artifact", text)


if __name__ == "__main__":
    unittest.main()
