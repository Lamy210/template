from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.homebrew.parse_release_checksum import parse_release_checksum


REPO_ROOT = Path(__file__).resolve().parents[2]
PARSER = REPO_ROOT / "scripts/homebrew/parse_release_checksum.py"
DIGEST = "0123456789abcdef" * 4


class ReleaseChecksumTests(unittest.TestCase):
    def test_accepts_exact_canonical_shasum_line(self) -> None:
        self.assertEqual(
            DIGEST,
            parse_release_checksum(
                f"{DIGEST}  MyApp-v1.2.3.dmg\n",
                expected_filename="MyApp-v1.2.3.dmg",
            ),
        )

    def test_rejects_wrong_filename(self) -> None:
        with self.assertRaisesRegex(ValueError, "filename mismatch"):
            parse_release_checksum(
                f"{DIGEST}  Other-v1.2.3.dmg\n",
                expected_filename="MyApp-v1.2.3.dmg",
            )

    def test_rejects_extra_lines_or_trailing_data(self) -> None:
        for payload in (
            f"{DIGEST}  MyApp-v1.2.3.dmg\nextra\n",
            f"{DIGEST}  MyApp-v1.2.3.dmg\n{DIGEST}  Other.dmg\n",
            f"{DIGEST}  MyApp-v1.2.3.dmg",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_release_checksum(
                        payload,
                        expected_filename="MyApp-v1.2.3.dmg",
                    )

    def test_rejects_noncanonical_digest_or_spacing(self) -> None:
        for payload in (
            f"{DIGEST.upper()}  MyApp-v1.2.3.dmg\n",
            f"{DIGEST} MyApp-v1.2.3.dmg\n",
            f"sha256:{DIGEST}  MyApp-v1.2.3.dmg\n",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_release_checksum(
                        payload,
                        expected_filename="MyApp-v1.2.3.dmg",
                    )

    def test_rejects_unsafe_expected_filename(self) -> None:
        with self.assertRaises(ValueError):
            parse_release_checksum(
                f"{DIGEST}  MyApp.dmg\n",
                expected_filename="../MyApp.dmg",
            )

    def test_cli_prints_digest_for_canonical_asset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            checksum = Path(temporary_directory) / "MyApp-v1.2.3.dmg.sha256"
            checksum.write_text(
                f"{DIGEST}  MyApp-v1.2.3.dmg\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(PARSER),
                    str(checksum),
                    "MyApp-v1.2.3.dmg",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(DIGEST, result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
