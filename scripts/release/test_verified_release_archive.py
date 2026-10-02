from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts.release import verified_release_archive
from scripts.release.verified_release_archive import (
    MAX_METADATA_BYTES,
    validate_and_extract_verified_release_artifact,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/extract-verified-release-artifact.py"
DMG_NAME = "MyApp-v1.2.3.dmg"


def write_zip(
    path: Path,
    entries: list[tuple[zipfile.ZipInfo, bytes]],
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for info, payload in entries:
            archive.writestr(info, payload)


def regular_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class VerifiedReleaseArchiveTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        archive = root / "verified-release.zip"
        output = root / "release-output"
        write_zip(
            archive,
            [
                (regular_info(DMG_NAME), b"trusted-dmg"),
                (regular_info(f"{DMG_NAME}.sha256"), b"checksum\n"),
                (
                    regular_info("release-provenance.json"),
                    b'{"schemaVersion":1}\n',
                ),
            ],
        )
        return temporary_directory, archive, output

    def test_accepts_exact_digest_bound_three_file_payload(self) -> None:
        _, archive, output = self.fixture()

        errors = validate_and_extract_verified_release_artifact(
            archive,
            output,
            dmg_name=DMG_NAME,
            expected_digest=digest(archive),
        )

        self.assertEqual([], errors)
        self.assertEqual(b"trusted-dmg", (output / DMG_NAME).read_bytes())
        self.assertEqual(
            {"release-provenance.json", DMG_NAME, f"{DMG_NAME}.sha256"},
            {entry.name for entry in output.iterdir()},
        )

    def test_rejects_raw_artifact_digest_mismatch(self) -> None:
        _, archive, output = self.fixture()

        errors = validate_and_extract_verified_release_artifact(
            archive,
            output,
            dmg_name=DMG_NAME,
            expected_digest="sha256:" + "0" * 64,
        )

        self.assertTrue(any("digest mismatch" in error for error in errors), errors)
        self.assertFalse(output.exists())

    def test_source_mutation_after_snapshot_does_not_change_extracted_bytes(self) -> None:
        _, archive, output = self.fixture()
        expected_digest = digest(archive)
        original_sha256_file = verified_release_archive._sha256_file

        def mutate_original_then_hash(snapshot_path: Path) -> str:
            archive.write_bytes(b"tampered-after-snapshot")
            return original_sha256_file(snapshot_path)

        with mock.patch.object(
            verified_release_archive,
            "_sha256_file",
            side_effect=mutate_original_then_hash,
        ):
            errors = validate_and_extract_verified_release_artifact(
                archive,
                output,
                dmg_name=DMG_NAME,
                expected_digest=expected_digest,
            )

        self.assertEqual([], errors)
        self.assertEqual(b"trusted-dmg", (output / DMG_NAME).read_bytes())
        self.assertEqual(b"tampered-after-snapshot", archive.read_bytes())

    def test_rejects_unexpected_or_duplicate_members(self) -> None:
        for extra_entries in (
            [(regular_info("extra.txt"), b"extra")],
            [(regular_info(DMG_NAME), b"duplicate")],
        ):
            with self.subTest(entries=[item[0].filename for item in extra_entries]):
                _, archive, output = self.fixture()
                with zipfile.ZipFile(archive, "a") as zip_file:
                    for info, payload in extra_entries:
                        zip_file.writestr(info, payload)

                errors = validate_and_extract_verified_release_artifact(
                    archive,
                    output,
                    dmg_name=DMG_NAME,
                    expected_digest=digest(archive),
                )

                self.assertTrue(errors)
                self.assertFalse(output.exists())

    def test_rejects_symlink_member(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        archive = root / "verified-release.zip"
        output = root / "release-output"
        symlink = zipfile.ZipInfo(DMG_NAME)
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        write_zip(
            archive,
            [
                (symlink, b"other"),
                (regular_info(f"{DMG_NAME}.sha256"), b"checksum\n"),
                (regular_info("release-provenance.json"), b"{}\n"),
            ],
        )

        errors = validate_and_extract_verified_release_artifact(
            archive,
            output,
            dmg_name=DMG_NAME,
            expected_digest=digest(archive),
        )

        self.assertTrue(any("symlink" in error for error in errors), errors)
        self.assertFalse(output.exists())

    def test_rejects_oversized_metadata_member(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        archive = root / "verified-release.zip"
        output = root / "release-output"
        write_zip(
            archive,
            [
                (regular_info(DMG_NAME), b"dmg"),
                (
                    regular_info(f"{DMG_NAME}.sha256"),
                    b"x" * (MAX_METADATA_BYTES + 1),
                ),
                (regular_info("release-provenance.json"), b"{}\n"),
            ],
        )

        errors = validate_and_extract_verified_release_artifact(
            archive,
            output,
            dmg_name=DMG_NAME,
            expected_digest=digest(archive),
        )

        self.assertTrue(any("size limit" in error for error in errors), errors)
        self.assertFalse(output.exists())

    def test_direct_cli_accepts_valid_raw_artifact(self) -> None:
        _, archive, output = self.fixture()
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--archive",
                str(archive),
                "--output",
                str(output),
                "--dmg-name",
                DMG_NAME,
                "--expected-digest",
                digest(archive),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"trusted-dmg", (output / DMG_NAME).read_bytes())


if __name__ == "__main__":
    unittest.main()
