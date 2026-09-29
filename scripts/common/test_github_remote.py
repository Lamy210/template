from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.common.github_remote import repository_from_github_remote


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/common/resolve-github-repository-from-remote.py"


class GithubRemoteTests(unittest.TestCase):
    def test_accepts_supported_github_remote_forms(self) -> None:
        cases = {
            "git@github.com:Example/Repo.git": "Example/Repo",
            "git@github.com:Example/Repo": "Example/Repo",
            "https://github.com/Example/Repo.git": "Example/Repo",
            "https://github.com/Example/Repo": "Example/Repo",
            "ssh://git@github.com/Example/Repo.git": "Example/Repo",
            "ssh://git@github.com:22/Example/Repo.git": "Example/Repo",
        }
        for remote, expected in cases.items():
            with self.subTest(remote=remote):
                self.assertEqual(expected, repository_from_github_remote(remote))

    def test_rejects_ambiguous_or_unsafe_remote_forms(self) -> None:
        for remote in (
            "",
            " git@github.com:Example/Repo.git",
            "git@github.com:../Repo.git",
            "git@github.com:Example/..git",
            "git@github.com:Example/Repo/extra.git",
            "git@example.com:Example/Repo.git",
            "http://github.com/Example/Repo.git",
            "https://token@github.com/Example/Repo.git",
            "https://github.com:443/Example/Repo.git",
            "https://github.com/Example/Repo.git?x=1",
            "https://github.com/Example/Repo.git#fragment",
            "ssh://user@github.com/Example/Repo.git",
            "ssh://git@github.com:2222/Example/Repo.git",
            "https://evil.example/Example/Repo.git",
        ):
            with self.subTest(remote=remote):
                with self.assertRaises(ValueError):
                    repository_from_github_remote(remote)

    def test_cli_is_package_safe_outside_repository_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "git@github.com:Example/Repo.git",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("Example/Repo", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
