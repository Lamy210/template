from __future__ import annotations

import io
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from scripts.release.actions_artifact import validate_and_extract_release_artifact


EXPECTED_FILES = {
    "release-input/unsigned-macos-app.tar.gz",
    "release-input/build-provenance.json",
}


def add_file(archive: zipfile.ZipFile, name: str, payload: bytes = b"fixture") -> None:
    archive.writestr(name, payload)


class ActionsArtifactValidationTests(unittest.TestCase):
    def create_zip(self, entries) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        path = Path(temporary_directory.name) / "artifact.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for entry in entries:
                if isinstance(entry, tuple):
                    info, payload = entry
                    archive.writestr(info, payload)
                else:
                    add_file(archive, entry)
        return temporary_directory, path

    def test_extracts_exact_expected_files(self) -> None:
        temporary_directory, archive_path = self.create_zip(sorted(EXPECTED_FILES))
        self.addCleanup(temporary_directory.cleanup)
        output = Path(temporary_directory.name) / "out"

        errors = validate_and_extract_release_artifact(archive_path, output)

        self.assertEqual([], errors)
        self.assertEqual(b"fixture", (output / "release-input/unsigned-macos-app.tar.gz").read_bytes())
        self.assertEqual(b"fixture", (output / "release-input/build-provenance.json").read_bytes())

    def test_rejects_path_traversal(self) -> None:
        temporary_directory, archive_path = self.create_zip(
            ["../escape", *sorted(EXPECTED_FILES)]
        )
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("traversal" in error for error in errors))

    def test_rejects_absolute_path(self) -> None:
        temporary_directory, archive_path = self.create_zip(
            ["/tmp/escape", *sorted(EXPECTED_FILES)]
        )
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("absolute" in error for error in errors))

    def test_rejects_drive_prefixed_path(self) -> None:
        temporary_directory, archive_path = self.create_zip(
            ["C:/escape", *sorted(EXPECTED_FILES)]
        )
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("drive" in error for error in errors))

    def test_rejects_duplicate_canonical_path(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        archive_path = Path(temporary_directory.name) / "artifact.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            add_file(archive, "release-input/unsigned-macos-app.tar.gz", b"first")
            add_file(archive, "release-input/./unsigned-macos-app.tar.gz", b"second")
            add_file(archive, "release-input/build-provenance.json")
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("duplicate" in error for error in errors))

    def test_rejects_symlink_entry(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        archive_path = Path(temporary_directory.name) / "artifact.zip"
        link = zipfile.ZipInfo("release-input/unsigned-macos-app.tar.gz")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(link, "../../escape")
            add_file(archive, "release-input/build-provenance.json")
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("symlink" in error for error in errors))

    def test_rejects_unexpected_file(self) -> None:
        temporary_directory, archive_path = self.create_zip(
            [*sorted(EXPECTED_FILES), "release-input/extra.txt"]
        )
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("unexpected files" in error for error in errors))

    def test_rejects_missing_expected_file(self) -> None:
        temporary_directory, archive_path = self.create_zip(
            ["release-input/build-provenance.json"]
        )
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("missing files" in error for error in errors))

    def test_rejects_member_count_above_limit(self) -> None:
        temporary_directory, archive_path = self.create_zip(sorted(EXPECTED_FILES))
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path,
            Path(temporary_directory.name) / "out",
            max_members=1,
        )
        self.assertTrue(any("member count" in error for error in errors))

    def test_rejects_total_uncompressed_size_above_limit(self) -> None:
        temporary_directory, archive_path = self.create_zip(sorted(EXPECTED_FILES))
        self.addCleanup(temporary_directory.cleanup)
        errors = validate_and_extract_release_artifact(
            archive_path,
            Path(temporary_directory.name) / "out",
            max_total_uncompressed_bytes=1,
        )
        self.assertTrue(any("uncompressed size" in error for error in errors))

    def test_rejects_invalid_resource_limits(self) -> None:
        temporary_directory, archive_path = self.create_zip(sorted(EXPECTED_FILES))
        self.addCleanup(temporary_directory.cleanup)
        output = Path(temporary_directory.name) / "out"

        member_errors = validate_and_extract_release_artifact(
            archive_path,
            output,
            max_members=0,
        )
        self.assertTrue(any("positive integer" in error for error in member_errors))

        size_errors = validate_and_extract_release_artifact(
            archive_path,
            output,
            max_total_uncompressed_bytes=True,
        )
        self.assertTrue(any("positive integer" in error for error in size_errors))

    def test_rejects_bad_zip(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        archive_path = Path(temporary_directory.name) / "artifact.zip"
        archive_path.write_bytes(b"not a zip")
        errors = validate_and_extract_release_artifact(
            archive_path, Path(temporary_directory.name) / "out"
        )
        self.assertTrue(any("invalid ZIP" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
