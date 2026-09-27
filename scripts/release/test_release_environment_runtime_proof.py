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


def run_script(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
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


def write_fake_gh(root: Path) -> Path:
    fake_gh = root / "gh"
    fake_gh.write_text(
        textwrap.dedent(
            r'''#!/usr/bin/env bash
            set -euo pipefail
            args="$*"

            : "${GH_STUB_STATE:?GH_STUB_STATE is required}"
            : "${GH_STUB_SCENARIO:?GH_STUB_SCENARIO is required}"

            emit_runs() {
              local count
              count="$(cat "${GH_STUB_STATE}" 2>/dev/null || printf '0')"
              case "${count}" in
                0)
                  printf '%s\n' '[{"total_count":0,"workflow_runs":[]}]'
                  ;;
                1)
                  printf '%s\n' '[{"total_count":1,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","event":"workflow_dispatch"}]}]'
                  ;;
                2)
                  printf '%s\n' '[{"total_count":2,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","event":"workflow_dispatch"}]},{"total_count":2,"workflow_runs":[{"id":101,"display_title":"Release Environment Negative Proof / proof-branch","head_branch":"environment-proof/proof","event":"workflow_dispatch"}]}]'
                  ;;
                *)
                  printf '%s\n' '[{"total_count":3,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","event":"workflow_dispatch"},{"id":101,"display_title":"Release Environment Negative Proof / proof-branch","head_branch":"environment-proof/proof","event":"workflow_dispatch"}]},{"total_count":3,"workflow_runs":[{"id":102,"display_title":"Release Environment Negative Proof / proof-tag","head_branch":"environment-proof-proof","event":"workflow_dispatch"}]}]'
                  ;;
              esac
            }

            emit_jobs() {
              local run_id="$1"
              local probe_conclusion
              case "${GH_STUB_SCENARIO}" in
                success)
                  if [[ "${run_id}" == 100 ]]; then
                    probe_conclusion="success"
                  else
                    probe_conclusion="failure"
                  fi
                  ;;
                default-denied)
                  probe_conclusion="failure"
                  ;;
                unauthorized-enters)
                  if [[ "${run_id}" == 100 || "${run_id}" == 101 ]]; then
                    probe_conclusion="success"
                  else
                    probe_conclusion="failure"
                  fi
                  ;;
                *)
                  exit 93
                  ;;
              esac

              printf '[{"total_count":2,"jobs":[{"id":%s1,"name":"Baseline runner","status":"completed","conclusion":"success"}]},' \
                "${run_id}"
              printf '{"total_count":2,"jobs":[{"id":%s2,"name":"Release environment probe","status":"completed","conclusion":"%s"}]}]\n' \
                "${run_id}" "${probe_conclusion}"
            }

            emit_run() {
              local run_id="$1"
              local conclusion
              case "${GH_STUB_SCENARIO}" in
                success)
                  if [[ "${run_id}" == 100 ]]; then
                    conclusion="success"
                  else
                    conclusion="failure"
                  fi
                  ;;
                default-denied)
                  conclusion="failure"
                  ;;
                unauthorized-enters)
                  if [[ "${run_id}" == 100 || "${run_id}" == 101 ]]; then
                    conclusion="success"
                  else
                    conclusion="failure"
                  fi
                  ;;
                *)
                  exit 93
                  ;;
              esac
              printf '{"status":"completed","conclusion":"%s"}\n' "${conclusion}"
            }

            if [[ "$1" == "workflow" && "$2" == "run" ]]; then
              count="$(cat "${GH_STUB_STATE}" 2>/dev/null || printf '0')"
              count=$((count + 1))
              printf '%s\n' "${count}" >"${GH_STUB_STATE}"
              exit 0
            fi

            if [[ "$1" != "api" ]]; then
              exit 90
            fi

            if [[ "${args}" == *"/actions/workflows/"*"/runs?event=workflow_dispatch&per_page=100"* ]]; then
              if [[ "${args}" != *"--paginate"* || "${args}" != *"--slurp"* ]]; then
                exit 94
              fi
              emit_runs
              exit 0
            fi

            if [[ "${args}" =~ actions/runs/([0-9]+)/jobs\?per_page=100 ]]; then
              if [[ "${args}" != *"--paginate"* || "${args}" != *"--slurp"* ]]; then
                exit 95
              fi
              emit_jobs "${BASH_REMATCH[1]}"
              exit 0
            fi

            if [[ "${args}" =~ actions/runs/([0-9]+)$ ]]; then
              emit_run "${BASH_REMATCH[1]}"
              exit 0
            fi

            if [[ "${args}" == *"contents/.github/workflows/release-environment-proof.yml"* ]]; then
              printf '%s\n' '{"type":"file"}'
              exit 0
            fi

            if [[ "${args}" == *"commits/main"* ]]; then
              printf '%s\n' '{"sha":"1111111111111111111111111111111111111111"}'
              exit 0
            fi

            if [[ "${args}" == *"git/ref/heads/environment-proof/proof"* ]] ||
               [[ "${args}" == *"git/ref/tags/environment-proof-proof"* ]]; then
              exit 1
            fi

            if [[ "${args}" == *"--method POST"* && "${args}" == *"/git/refs"* ]]; then
              printf '%s\n' '{"ref":"created"}'
              exit 0
            fi

            if [[ "${args}" == *"--method DELETE"* ]]; then
              exit 0
            fi

            if [[ "${args}" == *"repos/example/disposable"* ]]; then
              printf '%s\n' '{"default_branch":"main"}'
              exit 0
            fi

            exit 91
            '''
        ),
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    return fake_gh


def fake_env(root: Path, scenario: str) -> dict[str, str]:
    return {
        "PATH": f"{root}:{os.environ['PATH']}",
        "GITHUB_REPOSITORY": "example/template",
        "GH_STUB_STATE": str(root / "dispatch-state"),
        "GH_STUB_SCENARIO": scenario,
        "PROOF_NONCE": "proof",
        "PROOF_POLL_ATTEMPTS": "1",
        "PROOF_POLL_SECONDS": "0",
    }


class ReleaseEnvironmentRuntimeProofTests(unittest.TestCase):
    def test_example_workflow_is_manual_secret_free_and_targets_release(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("\n  push:", text)
        self.assertIn("permissions: {}", text)
        self.assertIn("environment: release", text)
        self.assertIn(
            "Release Environment Negative Proof / ${{ inputs.nonce }}",
            text,
        )
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

    def test_run_and_job_discovery_is_fully_paginated(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("gh run list", text)
        self.assertIn("runs?event=workflow_dispatch&per_page=100", text)
        self.assertIn("--paginate --slurp", text)
        self.assertIn("workflow-run pages disagree on total_count", text)
        self.assertIn(
            "workflow-run total_count={declared_total} does not match",
            text,
        )
        self.assertIn("workflow-run response contains duplicate id", text)
        self.assertIn('event != "workflow_dispatch"', text)
        self.assertIn("workflow jobs pages disagree on total_count", text)
        self.assertIn(
            "workflow jobs total_count={declared_total} does not match",
            text,
        )
        self.assertIn("workflow jobs response contains duplicate id", text)

    def test_contract_binds_dispatched_run_to_new_id_and_expected_ref(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("baseline_run_ids", text)
        self.assertIn("headBranch", text)
        self.assertIn("expected_ref", text)
        self.assertIn('"databaseId": run_id', text)
        self.assertIn('"displayTitle": title', text)

    def test_fake_github_proves_branch_and_tag_are_denied_across_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "success"),
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("default branch admitted", result.stdout)
        self.assertIn("unauthorized branch denied", result.stdout)
        self.assertIn("unauthorized tag denied", result.stdout)
        self.assertIn("release Environment negative runtime proof passed", result.stdout)

    def test_fake_github_fails_if_default_branch_cannot_enter_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "default-denied"),
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Expected authorized default run to succeed", result.stderr)

    def test_fake_github_fails_if_probe_enters_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "unauthorized-enters"),
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Expected unauthorized branch run to fail", result.stderr)


if __name__ == "__main__":
    unittest.main()
