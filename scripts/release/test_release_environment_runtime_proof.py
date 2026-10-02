from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from scripts.release.proof_workflow_input import (
    MAX_GITHUB_CONTENTS_JSON_BYTES,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/release/prove-release-environment-policy.sh"
VALIDATOR = (
    REPO_ROOT
    / "scripts/release/validate-release-environment-proof-workflow.py"
)
WORKFLOW = REPO_ROOT / "examples/release-environment-proof.yml"


def run_script(
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged["GITHUB_ACTIONS"] = "false"
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
              if [[ "${GH_STUB_SCENARIO}" == "default-head-drift" && "${count}" == 1 ]]; then
                printf '%s\n' '[{"total_count":1,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","head_sha":"2222222222222222222222222222222222222222","event":"workflow_dispatch"}]}]'
                return
              fi
              case "${count}" in
                0)
                  printf '%s\n' '[{"total_count":0,"workflow_runs":[]}]'
                  ;;
                1)
                  printf '%s\n' '[{"total_count":1,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","head_sha":"1111111111111111111111111111111111111111","event":"workflow_dispatch"}]}]'
                  ;;
                2)
                  printf '%s\n' '[{"total_count":2,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","head_sha":"1111111111111111111111111111111111111111","event":"workflow_dispatch"}]},{"total_count":2,"workflow_runs":[{"id":101,"display_title":"Release Environment Negative Proof / proof-branch","head_branch":"environment-proof/proof","head_sha":"1111111111111111111111111111111111111111","event":"workflow_dispatch"}]}]'
                  ;;
                *)
                  printf '%s\n' '[{"total_count":3,"workflow_runs":[{"id":100,"display_title":"Release Environment Negative Proof / proof-default","head_branch":"main","head_sha":"1111111111111111111111111111111111111111","event":"workflow_dispatch"},{"id":101,"display_title":"Release Environment Negative Proof / proof-branch","head_branch":"environment-proof/proof","head_sha":"1111111111111111111111111111111111111111","event":"workflow_dispatch"}]},{"total_count":3,"workflow_runs":[{"id":102,"display_title":"Release Environment Negative Proof / proof-tag","head_branch":"environment-proof-proof","head_sha":"1111111111111111111111111111111111111111","event":"workflow_dispatch"}]}]'
                  ;;
              esac
            }

            emit_jobs() {
              local run_id="$1"
              local probe_conclusion
              case "${GH_STUB_SCENARIO}" in
                success | repository-drift | final-head-drift | cleanup-failure)
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
                success | repository-drift | final-head-drift | cleanup-failure)
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
              printf '{"type":"file","path":".github/workflows/release-environment-proof.yml","sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","encoding":"base64","content":"%s"}\n' \
                "${GH_STUB_WORKFLOW_BASE64}"
              exit 0
            fi

            if [[ "${args}" == *"commits/main"* ]]; then
              count="$(cat "${GH_STUB_STATE}" 2>/dev/null || printf '0')"
              if [[ "${GH_STUB_SCENARIO}" == "final-head-drift" && "${count}" -ge 3 ]]; then
                printf '%s\n' '{"sha":"2222222222222222222222222222222222222222"}'
              else
                printf '%s\n' '{"sha":"1111111111111111111111111111111111111111"}'
              fi
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
              if [[ "${GH_STUB_SCENARIO}" == "cleanup-failure" &&
                    "${args}" == *"git/refs/tags/environment-proof-proof"* ]]; then
                exit 96
              fi
              exit 0
            fi

            if [[ "${args}" == *"repos/example/disposable"* ]]; then
              count="$(cat "${GH_STUB_STATE}" 2>/dev/null || printf '0')"
              if [[ "${GH_STUB_SCENARIO}" == "repository-drift" && "${count}" -ge 3 ]]; then
                printf '%s\n' '{"id":123,"full_name":"example/disposable","default_branch":"release-control"}'
              else
                printf '%s\n' '{"id":123,"full_name":"example/disposable","default_branch":"main"}'
              fi
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
        "GH_STUB_WORKFLOW_BASE64": base64.b64encode(
            WORKFLOW.read_bytes()
        ).decode("ascii"),
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

    def test_validator_rejects_oversized_stdin_before_json_parse(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--expected-path",
                ".github/workflows/release-environment-proof.yml",
                "--trusted-workflow",
                str(WORKFLOW),
            ],
            cwd=REPO_ROOT,
            input=" " * (MAX_GITHUB_CONTENTS_JSON_BYTES + 1),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("exceeds byte limit", result.stderr)

    def test_validator_rejects_symlinked_trusted_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            trusted = root / "trusted.yml"
            trusted.symlink_to(WORKFLOW)
            document = {
                "type": "file",
                "path": ".github/workflows/release-environment-proof.yml",
                "sha": "a" * 40,
                "encoding": "base64",
                "content": base64.b64encode(WORKFLOW.read_bytes()).decode(
                    "ascii"
                ),
            }
            metadata = root / "contents.json"
            metadata.write_text(json.dumps(document), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--github-content-json",
                    str(metadata),
                    "--expected-path",
                    ".github/workflows/release-environment-proof.yml",
                    "--trusted-workflow",
                    str(trusted),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("regular non-symlink file", result.stderr)

    def test_requires_explicit_disposable_confirmation(self) -> None:
        result = run_script("--repository", "example/disposable")
        self.assertEqual(2, result.returncode)
        self.assertIn("--confirm-disposable", result.stderr)

    def test_refuses_github_actions_execution(self) -> None:
        result = run_script(
            "--repository",
            "example/disposable",
            "--confirm-disposable",
            "example/disposable",
            env={"GITHUB_ACTIONS": "true"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn(
            "Refusing destructive disposable-repository proof from GitHub Actions",
            result.stderr,
        )

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

    def test_refuses_current_repository_case_insensitively(self) -> None:
        result = run_script(
            "--repository",
            "Example/Live",
            "--confirm-disposable",
            "Example/Live",
            env={"GITHUB_REPOSITORY": "example/live"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the current repository", result.stderr)

    def test_rejects_noncanonical_current_repository_identity(self) -> None:
        result = run_script(
            "--repository",
            "example/disposable",
            "--confirm-disposable",
            "example/disposable",
            env={"GITHUB_REPOSITORY": "../escape"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("GITHUB_REPOSITORY must use canonical owner/repo", result.stderr)

    def test_refuses_local_checkout_repository(self) -> None:
        result = run_script(
            "--repository",
            "Lamy210/template",
            "--confirm-disposable",
            "Lamy210/template",
            env={"GITHUB_REPOSITORY": ""},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the local checkout repository", result.stderr)

    def test_contract_requires_positive_default_and_negative_branch_tag_controls(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("GITHUB_ACTIONS", text)
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
        self.assertIn('git -C "${repo_root}" remote get-url origin', text)
        self.assertIn("github_repository_from_remote", text)
        self.assertIn("resolve-github-repository-from-remote.py", text)
        self.assertIn("same_repository", text)
        self.assertIn("refuses the local checkout repository", text)
        self.assertLess(
            text.index("GITHUB_ACTIONS"),
            text.index("--method POST"),
            "GitHub Actions refusal must run before temporary ref creation",
        )
        self.assertLess(
            text.index('git -C "${repo_root}" remote get-url origin'),
            text.index("--method POST"),
        )
        self.assertIn("validate-release-environment-proof-workflow.py", text)
        self.assertIn("examples/release-environment-proof.yml", text)
        self.assertLess(
            text.index("validate-release-environment-proof-workflow.py"),
            text.index("--method POST"),
        )
        self.assertIn(
            'nonce="${PROOF_NONCE:-$(date -u +%Y%m%d%H%M%S)-$$}"',
            text,
        )
        self.assertIn("cleanup_best_effort", text)
        self.assertIn("cleanup_refs_strict", text)
        self.assertIn("trap cleanup_best_effort EXIT", text)
        self.assertIn("trap - EXIT", text)
        self.assertLess(
            text.index("if ! cleanup_refs_strict; then"),
            text.index("release Environment negative runtime proof passed"),
        )

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
        self.assertIn('"headSha": head_sha', text)
        self.assertIn("expected_sha", text)
        self.assertIn('item.get("headSha") == expected_sha', text)
        self.assertIn('?ref=${default_sha}', text)
        self.assertEqual(
            2,
            text.count(
                'find_run_id "${title}" "${ref}" "${default_sha}" "${baseline_run_ids}"'
            ),
        )
        self.assertIn("repository id changed during Environment proof", text)
        self.assertIn("repository full_name changed during Environment proof", text)
        self.assertIn("repository default_branch changed during Environment proof", text)
        self.assertIn("default branch head changed during Environment proof", text)

    def test_refuses_modified_remote_proof_workflow_before_ref_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            env = fake_env(root, "success")
            env["GH_STUB_WORKFLOW_BASE64"] = base64.b64encode(
                WORKFLOW.read_bytes() + b"# unexpected remote change\n"
            ).decode("ascii")

            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=env,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn(
                "does not exactly match trusted example",
                result.stderr,
            )
            self.assertFalse((root / "dispatch-state").exists())

    def test_fails_if_default_branch_dispatch_uses_different_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "default-head-drift"),
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "Unable to locate fresh dispatched workflow run",
            result.stderr,
        )

    def test_fails_if_repository_default_branch_changes_before_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "repository-drift"),
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "repository default_branch changed during Environment proof",
            result.stderr,
        )
        self.assertNotIn(
            "release Environment negative runtime proof passed",
            result.stdout,
        )

    def test_fails_if_default_branch_head_changes_before_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "final-head-drift"),
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn(
            "default branch head changed during Environment proof",
            result.stderr,
        )
        self.assertNotIn(
            "release Environment negative runtime proof passed",
            result.stdout,
        )

    def test_fails_if_temporary_ref_cleanup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root)
            result = run_script(
                "--repository",
                "example/disposable",
                "--confirm-disposable",
                "example/disposable",
                env=fake_env(root, "cleanup-failure"),
            )

        self.assertEqual(4, result.returncode)
        self.assertIn(
            "Failed to delete temporary proof tag",
            result.stderr,
        )
        self.assertIn(
            "temporary ref cleanup failed",
            result.stderr,
        )
        self.assertNotIn(
            "release Environment negative runtime proof passed",
            result.stdout,
        )

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
