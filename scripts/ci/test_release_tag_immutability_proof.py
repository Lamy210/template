from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ci/prove-release-tag-immutability.sh"
INITIAL_SHA = "1" * 40
MOVE_SHA = "2" * 40


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


def proof_args(repository: str = "example/disposable-proof") -> tuple[str, ...]:
    return (
        "--repository",
        repository,
        "--confirm-disposable",
        repository,
        "--tag",
        "v0.0.1",
        "--initial-sha",
        INITIAL_SHA,
        "--move-sha",
        MOVE_SHA,
    )


def write_fake_gh(root: Path, scenario: str) -> Path:
    state = root / "state"
    fake_gh = root / "gh"
    fake_gh.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail

            state={state!s}
            scenario={scenario!r}
            args="$*"
            endpoint=""
            for argument in "$@"; do
              if [[ "$argument" == repos/* || "$argument" == /repos/* ]]; then
                endpoint="$argument"
              fi
            done

            if [[ "$endpoint" == "repos/example/disposable-proof" ]]; then
              if [[ "$scenario" == "repository-drift" && -f "$state" ]]; then
                printf '%s\n' '{{"id":124,"full_name":"example/disposable-proof"}}'
              else
                printf '%s\n' '{{"id":123,"full_name":"example/disposable-proof"}}'
              fi
              exit 0
            fi

            if [[ "$endpoint" == repos/example/disposable-proof/commits/* ]]; then
              printf '%s\n' '{{"sha":"ok"}}'
              exit 0
            fi

            if [[ "$endpoint" == "repos/example/disposable-proof/git/ref/tags/v0.0.1" ]]; then
              if [[ ! -f "$state" ]]; then
                exit 1
              fi
              sha="$(cat "$state")"
              ref="refs/tags/v0.0.1"
              object_type="commit"
              if [[ "$scenario" == "wrong-ref" ]]; then
                ref="refs/tags/v9.9.9"
              elif [[ "$scenario" == "wrong-object-type" ]]; then
                object_type="tag"
              fi
              printf '{{"ref":"%s","object":{{"type":"%s","sha":"%s"}}}}\n' \
                "$ref" "$object_type" "$sha"
              exit 0
            fi

            if [[ "$endpoint" == "repos/example/disposable-proof/git/refs" &&
                  "$args" == *"--method POST"* ]]; then
              printf '%s\n' "{INITIAL_SHA}" >"$state"
              printf '%s\n' '{{"ref":"refs/tags/v0.0.1"}}'
              exit 0
            fi

            if [[ "$endpoint" == "repos/example/disposable-proof/git/refs/tags/v0.0.1" &&
                  "$args" == *"--method PATCH"* ]]; then
              if [[ "$scenario" == "update-succeeds" ]]; then
                printf '%s\n' "{MOVE_SHA}" >"$state"
                printf '%s\n' '{{"ref":"refs/tags/v0.0.1"}}'
                exit 0
              fi
              if [[ "$scenario" == "non-ruleset-update" ]]; then
                echo "HTTP 403: Resource not accessible by integration" >&2
                exit 1
              fi
              echo "Repository rule violations found" >&2
              exit 1
            fi

            if [[ "$endpoint" == "repos/example/disposable-proof/git/refs/tags/v0.0.1" &&
                  "$args" == *"--method DELETE"* ]]; then
              echo "Repository rule violations found" >&2
              exit 1
            fi

            echo "unexpected fake gh invocation: $*" >&2
            exit 9
            """
        ),
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    return fake_gh


def fake_env(root: Path) -> dict[str, str]:
    return {
        "PATH": f"{root}:{os.environ['PATH']}",
        "GITHUB_REPOSITORY": "example/template",
    }


class ReleaseTagImmutabilityProofTests(unittest.TestCase):
    def test_requires_explicit_disposable_confirmation(self) -> None:
        result = run_script(
            "--repository",
            "example/disposable-proof",
            "--tag",
            "v0.0.1",
            "--initial-sha",
            INITIAL_SHA,
            "--move-sha",
            MOVE_SHA,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("--confirm-disposable", result.stderr)

    def test_rejects_current_repository_even_with_confirmation(self) -> None:
        result = run_script(
            *proof_args("example/live"),
            env={"GITHUB_REPOSITORY": "example/live"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the current repository", result.stderr)

    def test_rejects_current_repository_case_insensitively(self) -> None:
        result = run_script(
            *proof_args("Example/Live"),
            env={"GITHUB_REPOSITORY": "example/live"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the current repository", result.stderr)

    def test_rejects_local_checkout_repository_before_github_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_git = root / "git"
            fake_git.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    if [[ "$*" == *"remote get-url origin"* ]]; then
                      printf '%s\n' 'git@github.com:Lamy210/template.git'
                      exit 0
                    fi
                    exit 91
                    """
                ),
                encoding="utf-8",
            )
            fake_git.chmod(0o755)
            fake_gh = root / "gh"
            fake_gh.write_text(
                "#!/usr/bin/env bash\necho 'gh must not be called' >&2\nexit 92\n",
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                *proof_args("lamy210/TEMPLATE"),
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "",
                },
            )

        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the local checkout repository", result.stderr)

    def test_rejects_noncanonical_tag_or_equal_shas_before_gh(self) -> None:
        for tag, initial, move in (
            ("release-1", INITIAL_SHA, MOVE_SHA),
            ("v01.0.0", INITIAL_SHA, MOVE_SHA),
            ("v1.0.0", INITIAL_SHA, INITIAL_SHA),
        ):
            with self.subTest(tag=tag, initial=initial, move=move):
                result = run_script(
                    "--repository",
                    "example/disposable-proof",
                    "--confirm-disposable",
                    "example/disposable-proof",
                    "--tag",
                    tag,
                    "--initial-sha",
                    initial,
                    "--move-sha",
                    move,
                )
                self.assertEqual(2, result.returncode)

    def test_contract_guards_target_before_mutation_and_rebinds_identity(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("same_repository", text)
        self.assertNotIn("mapfile", text)
        self.assertNotIn(",,}", text)
        self.assertIn('git -C "${repo_root}" remote get-url origin', text)
        self.assertIn("github_repository_from_remote", text)
        self.assertIn("repository_identity", text)
        self.assertIn("require_repository_identity_stable", text)
        self.assertGreaterEqual(
            text.count("require_repository_identity_stable"),
            5,
        )
        self.assertLess(
            text.index('git -C "${repo_root}" remote get-url origin'),
            text.index("--method POST"),
        )
        self.assertLess(
            text.index('initial_identity_output="$(repository_identity)"'),
            text.index("--method POST"),
        )

    def test_contract_uses_create_then_rejected_update_and_delete_with_exact_readback(
        self,
    ) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--method POST", text)
        self.assertIn("git/refs", text)
        self.assertIn("--method PATCH", text)
        self.assertIn("--method DELETE", text)
        self.assertIn("force=true", text)
        self.assertIn("ref_sha", text)
        self.assertIn('document.get("ref") != expected_ref', text)
        self.assertIn('obj.get("type") != "commit"', text)
        self.assertIn("still points to initial SHA", text)
        self.assertIn("still exists after rejected deletion", text)

    def test_success_with_fake_github_api_proves_creation_and_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root, "success")
            result = run_script(*proof_args(), env=fake_env(root))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("creation succeeded", result.stdout)
        self.assertIn("update rejected", result.stdout)
        self.assertIn("deletion rejected", result.stdout)
        self.assertIn("release-tag immutability proof passed", result.stdout)

    def test_fails_if_repository_identity_drifts_after_tag_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root, "repository-drift")
            result = run_script(*proof_args(), env=fake_env(root))

        self.assertNotEqual(0, result.returncode)
        self.assertIn("identity changed", result.stderr)
        self.assertNotIn("update rejected", result.stdout)

    def test_fails_if_readback_ref_identity_is_wrong(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root, "wrong-ref")
            result = run_script(*proof_args(), env=fake_env(root))

        self.assertNotEqual(0, result.returncode)
        self.assertIn("tag ref identity mismatch", result.stderr)

    def test_fails_if_readback_is_not_a_lightweight_commit_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root, "wrong-object-type")
            result = run_script(*proof_args(), env=fake_env(root))

        self.assertNotEqual(0, result.returncode)
        self.assertIn("must resolve directly to a commit", result.stderr)

    def test_fails_if_update_is_rejected_for_non_ruleset_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root, "non-ruleset-update")
            result = run_script(*proof_args(), env=fake_env(root))

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not a confirmed repository-rule rejection", result.stderr)

    def test_fails_if_update_unexpectedly_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_fake_gh(root, "update-succeeds")
            result = run_script(*proof_args(), env=fake_env(root))

        self.assertNotEqual(0, result.returncode)
        self.assertIn("update unexpectedly succeeded", result.stderr)


if __name__ == "__main__":
    unittest.main()
