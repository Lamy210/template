from __future__ import annotations

import hashlib
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from scripts.release.runtime_proof_artifact import extract_runtime_proof_metadata


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_zip(path: Path, entries: list[tuple[zipfile.ZipInfo, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for info, payload in entries:
            archive.writestr(info, payload)


class RuntimeProofArtifactTests(unittest.TestCase):
    def fixture(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        archive = root / "artifact.zip"
        output = root / "metadata.json"
        return root, archive, output

    def test_extracts_unique_metadata_from_exact_digest(self) -> None:
        _, archive, output = self.fixture()
        metadata = zipfile.ZipInfo("validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(
            archive,
            [
                (metadata, b'{"schemaVersion":1}\n'),
                (app_archive, b"archive"),
            ],
        )

        self.assertEqual(
            [],
            extract_runtime_proof_metadata(
                archive,
                output,
                expected_digest=digest(archive),
            ),
        )
        self.assertEqual(b'{"schemaVersion":1}\n', output.read_bytes())

    def test_writes_actual_unsigned_archive_digest(self) -> None:
        root, archive, output = self.fixture()
        digest_output = root / "unsigned-archive-digest.txt"
        metadata = zipfile.ZipInfo("validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        app_payload = b"trusted-unsigned-archive"
        write_zip(
            archive,
            [
                (metadata, b'{"schemaVersion":1}\n'),
                (app_archive, app_payload),
            ],
        )

        self.assertEqual(
            [],
            extract_runtime_proof_metadata(
                archive,
                output,
                expected_digest=digest(archive),
                app_archive_digest_output_path=digest_output,
            ),
        )

        expected = "sha256:" + hashlib.sha256(app_payload).hexdigest()
        self.assertEqual(expected + "\n", digest_output.read_text(encoding="utf-8"))

    def test_rejects_unsigned_archive_over_size_limit(self) -> None:
        root, archive, output = self.fixture()
        digest_output = root / "unsigned-archive-digest.txt"
        metadata = zipfile.ZipInfo("validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(
            archive,
            [
                (metadata, b'{"schemaVersion":1}\n'),
                (app_archive, b"12345"),
            ],
        )

        errors = extract_runtime_proof_metadata(
            archive,
            output,
            expected_digest=digest(archive),
            app_archive_digest_output_path=digest_output,
            max_app_archive_bytes=4,
        )

        self.assertTrue(any("unsigned app archive exceeds" in error for error in errors))
        self.assertFalse(output.exists())
        self.assertFalse(digest_output.exists())

    def test_rejects_digest_mismatch(self) -> None:
        _, archive, output = self.fixture()
        metadata = zipfile.ZipInfo("validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(archive, [(metadata, b"{}\n"), (app_archive, b"archive")])

        errors = extract_runtime_proof_metadata(
            archive,
            output,
            expected_digest="sha256:" + "0" * 64,
        )

        self.assertTrue(any("digest mismatch" in error for error in errors))
        self.assertFalse(output.exists())

    def test_rejects_missing_or_duplicate_metadata(self) -> None:
        _, archive, output = self.fixture()
        other = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(archive, [(other, b"archive")])
        self.assertTrue(
            extract_runtime_proof_metadata(
                archive,
                output,
                expected_digest=digest(archive),
            )
        )

        archive.unlink()
        duplicate_a = zipfile.ZipInfo("validated-release-metadata.json")
        duplicate_b = zipfile.ZipInfo("validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(
            archive,
            [(duplicate_a, b"{}"), (duplicate_b, b"{}"), (app_archive, b"archive")],
        )
        errors = extract_runtime_proof_metadata(
            archive,
            output,
            expected_digest=digest(archive),
        )
        self.assertTrue(any("exactly one" in error for error in errors))

    def test_rejects_nested_metadata_path_even_with_matching_basename(self) -> None:
        _, archive, output = self.fixture()
        nested = zipfile.ZipInfo("nested/validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(archive, [(nested, b"{}\n"), (app_archive, b"archive")])

        errors = extract_runtime_proof_metadata(
            archive,
            output,
            expected_digest=digest(archive),
        )

        self.assertTrue(any("root-level" in error for error in errors))

    def test_rejects_missing_or_symlinked_unsigned_archive(self) -> None:
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                _, archive, output = self.fixture()
                metadata = zipfile.ZipInfo("validated-release-metadata.json")
                entries = [(metadata, b"{}\n")]
                if symlink:
                    app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
                    app_archive.create_system = 3
                    app_archive.external_attr = (stat.S_IFLNK | 0o777) << 16
                    entries.append((app_archive, b"target"))
                write_zip(archive, entries)

                errors = extract_runtime_proof_metadata(
                    archive,
                    output,
                    expected_digest=digest(archive),
                )

                self.assertTrue(any("unsigned app archive" in error for error in errors))

    def test_rejects_symlink_metadata_entry(self) -> None:
        _, archive, output = self.fixture()
        info = zipfile.ZipInfo("validated-release-metadata.json")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(archive, [(info, b"target"), (app_archive, b"archive")])

        errors = extract_runtime_proof_metadata(
            archive,
            output,
            expected_digest=digest(archive),
        )

        self.assertTrue(any("symbolic link" in error for error in errors))

    def test_rejects_metadata_over_size_limit(self) -> None:
        _, archive, output = self.fixture()
        info = zipfile.ZipInfo("validated-release-metadata.json")
        app_archive = zipfile.ZipInfo("unsigned-macos-app.tar.gz")
        write_zip(archive, [(info, b"12345"), (app_archive, b"archive")])

        errors = extract_runtime_proof_metadata(
            archive,
            output,
            expected_digest=digest(archive),
            max_metadata_bytes=4,
        )

        self.assertTrue(any("size limit" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
