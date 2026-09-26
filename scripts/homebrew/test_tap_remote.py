from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import unittest

from scripts.homebrew.tap_remote import validate_tap_remote_urls


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/homebrew/validate-tap-remote.py"
HTTPS = "https://github.com/example/homebrew-tap"
SSH = "git@github.com:example/homebrew-tap.git"


class TapRemoteTests(unittest.TestCase):
    def validate(self, fetch_url: str, push_url: str) -> list[str]:
        return validate_tap_remote_urls(
            fetch_url=fetch_url,
            push_url=push_url,
            canonical_https_url=HTTPS,
            canonical_ssh_url=SSH,
        )

    def test_accepts_canonical_https_clone_url(self) -> None:
        self.assertEqual([], self.validate(f"{HTTPS}.git", f"{HTTPS}.git"))

    def test_accepts_canonical_https_web_form(self) -> None:
        self.assertEqual([], self.validate(HTTPS, HTTPS))

    def test_accepts_canonical_ssh_url(self) -> None:
        self.assertEqual([], self.validate(SSH, SSH))

    def test_accepts_fetch_and_push_using_different_canonical_protocols(self) -> None:
        self.assertEqual([], self.validate(f"{HTTPS}.git", SSH))

    def test_rejects_sibling_repository(self) -> None:
        errors = self.validate(
            "https://github.com/example/other.git",
            "https://github.com/example/other.git",
        )
        self.assertTrue(any("fetch URL" in error for error in errors))
        self.assertTrue(any("push URL" in error for error in errors))

    def test_rejects_mirror_or_rewrite_target(self) -> None:
        errors = self.validate(
            "ssh://git@mirror.example/example/homebrew-tap.git",
            SSH,
        )
        self.assertTrue(any("fetch URL" in error for error in errors))

    def test_rejects_embedded_credentials(self) -> None:
        errors = self.validate(
            "https://token@github.com/example/homebrew-tap.git",
            f"{HTTPS}.git",
        )
        self.assertTrue(any("fetch URL" in error for error in errors))

    def test_rejects_multiple_effective_push_urls(self) -> None:
        errors = self.validate(
            f"{HTTPS}.git",
            f"{HTTPS}.git\nhttps://github.com/example/other.git",
        )
        self.assertTrue(any("single canonical line" in error for error in errors))

    def test_rejects_multiline_remote(self) -> None:
        errors = self.validate(f"{HTTPS}.git\nhttps://evil.example/repo.git", SSH)
        self.assertTrue(any("single canonical line" in error for error in errors))

    def test_cli_rejects_unbound_push_remote(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                f"--fetch-url={HTTPS}.git",
                "--push-url=https://github.com/example/other.git",
                f"--canonical-https-url={HTTPS}",
                f"--canonical-ssh-url={SSH}",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("push URL", result.stderr)


if __name__ == "__main__":
    unittest.main()
