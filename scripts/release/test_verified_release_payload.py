from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.verified_release_payload import validate_verified_release_payload


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/validate-verified-release-payload.py"
DMG_NAME = "MyApp-1.2.3.dmg"


def write_valid_payload(root: Path) -> None:
    (root / DMG_NAME).write_bytes(b"dmg\n")
    (root / f"{DMG_NAME}.sha256").write_text("checksum\n", encoding="utf-8")
    (root / "release-provenance.json").write_text("{}\n", encoding="utf-8")


class VerifiedReleasePayloadTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name) / "release-output"
        root.mkdir()
        write_valid_payload(root)
        return temporary_directory, root

    def test_accepts_exact_three_file_payload(self) -> None:
        _, root = self.fixture()
        self.assertEqual([], validate_verified_release_payload(root, DMG_NAME))

    def test_rejects_missing_and_unexpected_entries(self) -> None:
        _, root = self.fixture()
        (root / "release-provenance.json").unlink()
        (root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")

        errors = validate_verified_release_payload(root, DMG_NAME)

        self.assertTrue(any("missing entries" in error for error in errors))
        self.assertTrue(any("unexpected entries" in error for error in errors))

    def test_rejects_nested_or_directory_payload_entries(self) -> None:
        _, root = self.fixture()
        extra = root / "debug"
        extra.mkdir()
        (extra / "symbols.txt").write_text("debug\n", encoding="utf-8")

        errors = validate_verified_release_payload(root, DMG_NAME)

        self.assertTrue(any("unexpected entries" in error for error in errors))

    def test_rejects_symlinked_expected_entry(self) -> None:
        _, root = self.fixture()
        provenance = root / "release-provenance.json"
        target = root / "real-provenance.json"
        provenance.rename(target)
        provenance.symlink_to(target.name)

        errors = validate_verified_release_payload(root, DMG_NAME)

        self.assertTrue(any("non-symlink" in error for error in errors))
        self.assertTrue(any("unexpected entries" in error for error in errors))

    def test_cli_rejects_extra_payload_before_publication_boundary(self) -> None:
        _, root = self.fixture()
        (root / "extra.bin").write_bytes(b"extra")

        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--root",
                str(root),
                "--dmg-name",
                DMG_NAME,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("unexpected entries", result.stderr)


if __name__ == "__main__":
    unittest.main()
