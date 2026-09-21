from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/ci/prove-release-tag-immutability.sh"


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


class ReleaseTagImmutabilityProofTests(unittest.TestCase):
    def test_requires_explicit_disposable_confirmation(self) -> None:
        result = run_script(
            "--repository", "example/disposable-proof",
            "--tag", "v0.0.1",
            "--initial-sha", "1" * 40,
            "--move-sha", "2" * 40,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("--confirm-disposable", result.stderr)

    def test_rejects_current_repository_even_with_confirmation(self) -> None:
        result = run_script(
            "--repository", "example/live",
            "--confirm-disposable", "example/live",
            "--tag", "v0.0.1",
            "--initial-sha", "1" * 40,
            "--move-sha", "2" * 40,
            env={"GITHUB_REPOSITORY": "example/live"},
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("refuses the current repository", result.stderr)

    def test_rejects_noncanonical_tag_or_equal_shas_before_gh(self) -> None:
        for tag, initial, move in (
            ("release-1", "1" * 40, "2" * 40),
            ("v01.0.0", "1" * 40, "2" * 40),
            ("v1.0.0", "1" * 40, "1" * 40),
        ):
            with self.subTest(tag=tag, initial=initial, move=move):
                result = run_script(
                    "--repository", "example/disposable-proof",
                    "--confirm-disposable", "example/disposable-proof",
                    "--tag", tag,
                    "--initial-sha", initial,
                    "--move-sha", move,
                )
                self.assertEqual(2, result.returncode)

    def test_contract_uses_create_then_rejected_update_and_delete_with_readback(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("--method POST", text)
        self.assertIn("git/refs", text)
        self.assertIn("--method PATCH", text)
        self.assertIn("--method DELETE", text)
        self.assertIn("force=true", text)
        self.assertIn("ref_sha", text)
        self.assertIn("still points to initial SHA", text)
        self.assertIn("still exists after rejected deletion", text)

    def test_success_with_fake_github_api_proves_creation_and_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state = root / "state"
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    f"""                    #!/usr/bin/env bash
                    set -euo pipefail
                    state={state!s}
                    args="$*"
                    if [[ "$args" == *"repos/example/disposable-proof/commits/"* ]]; then
                      printf '{{"sha":"ok"}}\n'
                      exit 0
                    fi
                    if [[ "$args" == *"repos/example/disposable-proof/git/ref/tags/v0.0.1"* ]]; then
                      if [[ ! -f "$state" ]]; then
                        exit 1
                      fi
                      sha="$(cat "$state")"
                      printf '{{"object":{{"sha":"%s"}}}}\n' "$sha"
                      exit 0
                    fi
                    if [[ "$args" == *"--method POST"* && "$args" == *"git/refs"* ]]; then
                      printf '%s\n' '{"1"*40}' >"$state"
                      printf '{{"ref":"refs/tags/v0.0.1"}}\n'
                      exit 0
                    fi
                    if [[ "$args" == *"--method PATCH"* ]]; then
                      echo "Repository rule violations found" >&2
                      exit 1
                    fi
                    if [[ "$args" == *"--method DELETE"* ]]; then
                      echo "Repository rule violations found" >&2
                      exit 1
                    fi
                    exit 9
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                "--repository", "example/disposable-proof",
                "--confirm-disposable", "example/disposable-proof",
                "--tag", "v0.0.1",
                "--initial-sha", "1" * 40,
                "--move-sha", "2" * 40,
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "example/template",
                },
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("creation succeeded", result.stdout)
        self.assertIn("update rejected", result.stdout)
        self.assertIn("deletion rejected", result.stdout)
        self.assertIn("release-tag immutability proof passed", result.stdout)

    def test_fails_if_update_is_rejected_for_non_ruleset_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state = root / "state"
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    f"""                    #!/usr/bin/env bash
                    set -euo pipefail
                    state={state!s}
                    args="$*"
                    if [[ "$args" == *"repos/example/disposable-proof/commits/"* ]]; then
                      printf '{{"sha":"ok"}}\n'
                      exit 0
                    fi
                    if [[ "$args" == *"repos/example/disposable-proof/git/ref/tags/v0.0.1"* ]]; then
                      if [[ ! -f "$state" ]]; then exit 1; fi
                      sha="$(cat "$state")"
                      printf '{{"object":{{"sha":"%s"}}}}\n' "$sha"
                      exit 0
                    fi
                    if [[ "$args" == *"--method POST"* ]]; then
                      printf '%s\n' '{"1"*40}' >"$state"
                      exit 0
                    fi
                    if [[ "$args" == *"--method PATCH"* ]]; then
                      echo "HTTP 403: Resource not accessible by integration" >&2
                      exit 1
                    fi
                    exit 9
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                "--repository", "example/disposable-proof",
                "--confirm-disposable", "example/disposable-proof",
                "--tag", "v0.0.1",
                "--initial-sha", "1" * 40,
                "--move-sha", "2" * 40,
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "example/template",
                },
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("not a confirmed repository-rule rejection", result.stderr)

    def test_fails_if_update_unexpectedly_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            state = root / "state"
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    f"""                    #!/usr/bin/env bash
                    set -euo pipefail
                    state={state!s}
                    args="$*"
                    if [[ "$args" == *"repos/example/disposable-proof/commits/"* ]]; then
                      printf '{{"sha":"ok"}}\n'
                      exit 0
                    fi
                    if [[ "$args" == *"repos/example/disposable-proof/git/ref/tags/v0.0.1"* ]]; then
                      if [[ ! -f "$state" ]]; then exit 1; fi
                      sha="$(cat "$state")"
                      printf '{{"object":{{"sha":"%s"}}}}\n' "$sha"
                      exit 0
                    fi
                    if [[ "$args" == *"--method POST"* ]]; then
                      printf '%s\n' '{"1"*40}' >"$state"
                      exit 0
                    fi
                    if [[ "$args" == *"--method PATCH"* ]]; then
                      printf '%s\n' '{"2"*40}' >"$state"
                      exit 0
                    fi
                    exit 9
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            result = run_script(
                "--repository", "example/disposable-proof",
                "--confirm-disposable", "example/disposable-proof",
                "--tag", "v0.0.1",
                "--initial-sha", "1" * 40,
                "--move-sha", "2" * 40,
                env={
                    "PATH": f"{root}:{os.environ['PATH']}",
                    "GITHUB_REPOSITORY": "example/template",
                },
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("update unexpectedly succeeded", result.stderr)


if __name__ == "__main__":
    unittest.main()
