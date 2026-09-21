from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/release/prove-release-environment-policy.sh"
WORKFLOW = REPO_ROOT / "examples/release-environment-proof.yml"


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


class ReleaseEnvironmentRuntimeProofTests(unittest.TestCase):
    def test_example_workflow_is_manual_secret_free_and_targets_release(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("\n  push:", text)
        self.assertIn("permissions: {}", text)
        self.assertIn("environment: release", text)
        self.assertIn("Release Environment Negative Proof / ${{ inputs.nonce }}", text)
        self.assertIn("Baseline runner", text)
        self.assertIn("Release environment probe", text)
        self.assertNotIn("secrets.", text)

    def test_requires_explicit_disposable_confirmation(self) -> None:
        result = run_script("--repository", "example/disposable")
        self.assertEqual(2, result.returncode)
        self.assertIn("--confirm-disposable", result.stderr)

    def test_refuses_current_repository(self) -> None:
        result = run_script(
            "--repository",
            "example/live",
            "--confirm-disposable",
            "example/live",
            env={"GITHUB_REPOSITORY": "example/live"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the current repository", result.stderr)

    def test_contract_requires_positive_default_and_negative_branch_tag_controls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("gh workflow run", text)
        self.assertIn("refs/heads/", text)
        self.assertIn("refs/tags/", text)
        self.assertIn("Baseline runner", text)
        self.assertIn("Release environment probe", text)
        self.assertIn("prove_ref_allowed", text)
        self.assertIn('prove_ref_allowed "${default_branch}" default', text)
        self.assertIn("default branch admitted by release Environment policy", text)
        self.assertIn("probe job must fail", text)
        self.assertIn("--method DELETE", text)

    def test_fake_github_proves_branch_and_tag_are_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    """                    #!/usr/bin/env bash
                    set -euo pipefail
                    args="$*"

                    if [[ "$1" == "workflow" && "$2" == "run" ]]; then
                      exit 0
                    fi

                    if [[ "$1" == "run" && "$2" == "list" ]]; then
                      printf '%s\n' '[{"databaseId":100,"displayTitle":"Release Environment Negative Proof / proof-default"},{"databaseId":101,"displayTitle":"Release Environment Negative Proof / proof-branch"},{"databaseId":102,"displayTitle":"Release Environment Negative Proof / proof-tag"}]'
                      exit 0
                    fi

                    if [[ "$1" != "api" ]]; then
                      exit 90
                    fi

                    if [[ "$args" == *"repos/example/disposable/actions/runs/100/jobs"* ]]; then
                      printf '%s\n' '{"jobs":[{"name":"Baseline runner","status":"completed","conclusion":"success"},{"name":"Release environment probe","status":"completed","conclusion":"success"}]}'
                      exit 0
                    fi
                    if [[ "$args" == *"repos/example/disposable/actions/runs/101/jobs"* ]] ||
                       [[ "$args" == *"repos/example/disposable/actions/runs/102/jobs"* ]]; then
                      printf '%s\n' '{"jobs":[{"name":"Baseline runner","status":"completed","conclusion":"success"},{"name":"Release environment probe","status":"completed","conclusion":"failure"}]}'
                      exit 0
                    fi

                    if [[ "$args" == *"repos/example/disposable/actions/runs/100"* ]]; then
                      printf '%s\n' '{"status":"completed","conclusion":"success"}'
                      exit 0
                    fi
                    if [[ "$args" == *"repos/example/disposable/actions/runs/101"* ]] ||
                       [[ "$args" == *"repos/example/disposable/actions/runs/102"* ]]; then
                      printf '%s\n' '{"status":"completed","conclusion":"failure"}'
                      exit 0
                    fi

                    if [[ "$args" == *"repos/example/disposable/contents/.github/workflows/release-environment-proof.yml"* ]]; then
                      printf '%s\n' '{"type":"file"}'
                      exit 0
                    fi

                    if [[ "$args" == *"repos/example/disposable/commits/main"* ]]; then
                      printf '%s\n' '{"sha":"1111111111111111111111111111111111111111"}'
                      exit 0
                    fi

                    if [[ "$args" == *"repos/example/disposable/git/ref/heads/environment-proof/proof"* ]] ||
                       [[ "$args" == *"repos/example/disposable/git/ref/tags/environment-proof-proof"* ]]; then
                      exit 1
                    fi

                    if [[ "$args" == *"--method POST"* && "$args" == *"repos/example/disposable/git/refs"* ]]; then
                      printf '%s\n' '{"ref":"created"}'
                      exit 0
                    fi

                    if [[ "$args" == *"--method DELETE"* ]]; then
                      exit 0
                    fi

                    if [[ "$args" == *"repos/example/disposable"* ]]; then
                      printf '%s\n' '{"default_branch":"main"}'
                      exit 0
                    fi

                    exit 91
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "example/template",
                    "PROOF_NONCE": "proof",
                    "PROOF_POLL_ATTEMPTS": "1",
                    "PROOF_POLL_SECONDS": "0",
                },
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("default branch admitted", result.stdout)
        self.assertIn("unauthorized branch denied", result.stdout)
        self.assertIn("unauthorized tag denied", result.stdout)
        self.assertIn("release Environment negative runtime proof passed", result.stdout)

    def test_fake_github_fails_if_default_branch_cannot_enter_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    """                    #!/usr/bin/env bash
                    set -euo pipefail
                    args="$*"

                    if [[ "$1" == "workflow" && "$2" == "run" ]]; then
                      exit 0
                    fi

                    if [[ "$1" == "run" && "$2" == "list" ]]; then
                      printf '%s\n' '[{"databaseId":100,"displayTitle":"Release Environment Negative Proof / proof-default"},{"databaseId":101,"displayTitle":"Release Environment Negative Proof / proof-branch"},{"databaseId":102,"displayTitle":"Release Environment Negative Proof / proof-tag"}]'
                      exit 0
                    fi

                    if [[ "$1" != "api" ]]; then
                      exit 90
                    fi

                    if [[ "$args" == *"actions/runs/100/jobs"* ]] ||
                       [[ "$args" == *"actions/runs/101/jobs"* ]] ||
                       [[ "$args" == *"actions/runs/102/jobs"* ]]; then
                      printf '%s\n' '{"jobs":[{"name":"Baseline runner","status":"completed","conclusion":"success"},{"name":"Release environment probe","status":"completed","conclusion":"failure"}]}'
                      exit 0
                    fi

                    if [[ "$args" == *"actions/runs/100"* ]] ||
                       [[ "$args" == *"actions/runs/101"* ]] ||
                       [[ "$args" == *"actions/runs/102"* ]]; then
                      printf '%s\n' '{"status":"completed","conclusion":"failure"}'
                      exit 0
                    fi

                    if [[ "$args" == *"contents/.github/workflows/release-environment-proof.yml"* ]]; then
                      printf '%s\n' '{"type":"file"}'
                      exit 0
                    fi
                    if [[ "$args" == *"commits/main"* ]]; then
                      printf '%s\n' '{"sha":"1111111111111111111111111111111111111111"}'
                      exit 0
                    fi
                    if [[ "$args" == *"git/ref/heads/environment-proof/proof"* ]] ||
                       [[ "$args" == *"git/ref/tags/environment-proof-proof"* ]]; then
                      exit 1
                    fi
                    if [[ "$args" == *"--method POST"* ]]; then exit 0; fi
                    if [[ "$args" == *"--method DELETE"* ]]; then exit 0; fi
                    if [[ "$args" == *"repos/example/disposable"* ]]; then
                      printf '%s\n' '{"default_branch":"main"}'
                      exit 0
                    fi
                    exit 91
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "example/template",
                    "PROOF_NONCE": "proof",
                    "PROOF_POLL_ATTEMPTS": "1",
                    "PROOF_POLL_SECONDS": "0",
                },
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Expected authorized default run to succeed", result.stderr)

    def test_fake_github_fails_if_probe_enters_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    """                    #!/usr/bin/env bash
                    set -euo pipefail
                    args="$*"

                    if [[ "$1" == "workflow" && "$2" == "run" ]]; then exit 0; fi
                    if [[ "$1" == "run" && "$2" == "list" ]]; then
                      printf '%s\n' '[{"databaseId":100,"displayTitle":"Release Environment Negative Proof / proof-default"},{"databaseId":101,"displayTitle":"Release Environment Negative Proof / proof-branch"}]'
                      exit 0
                    fi
                    if [[ "$1" != "api" ]]; then exit 90; fi
                    if [[ "$args" == *"actions/runs/100/jobs"* ]] ||
                       [[ "$args" == *"actions/runs/101/jobs"* ]]; then
                      printf '%s\n' '{"jobs":[{"name":"Baseline runner","status":"completed","conclusion":"success"},{"name":"Release environment probe","status":"completed","conclusion":"success"}]}'
                      exit 0
                    fi
                    if [[ "$args" == *"actions/runs/100"* ]] ||
                       [[ "$args" == *"actions/runs/101"* ]]; then
                      printf '%s\n' '{"status":"completed","conclusion":"success"}'
                      exit 0
                    fi
                    if [[ "$args" == *"contents/.github/workflows/release-environment-proof.yml"* ]]; then
                      printf '%s\n' '{"type":"file"}'
                      exit 0
                    fi
                    if [[ "$args" == *"commits/main"* ]]; then
                      printf '%s\n' '{"sha":"1111111111111111111111111111111111111111"}'
                      exit 0
                    fi
                    if [[ "$args" == *"git/ref/heads/environment-proof/proof"* ]] ||
                       [[ "$args" == *"git/ref/tags/environment-proof-proof"* ]]; then
                      exit 1
                    fi
                    if [[ "$args" == *"--method POST"* ]]; then exit 0; fi
                    if [[ "$args" == *"--method DELETE"* ]]; then exit 0; fi
                    if [[ "$args" == *"repos/example/disposable"* ]]; then
                      printf '%s\n' '{"default_branch":"main"}'
                      exit 0
                    fi
                    exit 91
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "example/template",
                    "PROOF_NONCE": "proof",
                    "PROOF_POLL_ATTEMPTS": "1",
                    "PROOF_POLL_SECONDS": "0",
                },
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Expected unauthorized branch run to fail", result.stderr)


if __name__ == "__main__":
    unittest.main()
