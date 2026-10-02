from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    copy_regular_file_bounded,
    snapshot_regular_file,
)


class SecureFileSnapshotTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source.bin"
        return temporary_directory, source

    def test_copies_regular_file_with_bound_and_stable_bytes(self) -> None:
        _, source = self.fixture()
        destination = source.parent / "copy.bin"
        source.write_bytes(b"trusted-copy")

        copied = copy_regular_file_bounded(
            source,
            destination,
            max_bytes=1024,
        )

        self.assertEqual(len(b"trusted-copy"), copied)
        self.assertEqual(b"trusted-copy", destination.read_bytes())
        self.assertEqual(0o600, destination.stat().st_mode & 0o777)

        source.write_bytes(b"changed")
        self.assertEqual(b"trusted-copy", destination.read_bytes())

    def test_bounded_copy_rejects_symlink_and_oversized_input(self) -> None:
        _, source = self.fixture()
        destination = source.parent / "copy.bin"
        target = source.parent / "target.bin"
        target.write_bytes(b"target")
        source.symlink_to(target.name)

        with self.assertRaises(RegularFileSnapshotError):
            copy_regular_file_bounded(
                source,
                destination,
                max_bytes=1024,
            )
        self.assertFalse(destination.exists())

        source.unlink()
        source.write_bytes(b"12345")
        with self.assertRaisesRegex(
            RegularFileSnapshotError,
            "exceeds copy byte limit",
        ):
            copy_regular_file_bounded(
                source,
                destination,
                max_bytes=4,
            )
        self.assertFalse(destination.exists())

    def test_bounded_copy_rejects_existing_destination(self) -> None:
        _, source = self.fixture()
        destination = source.parent / "copy.bin"
        source.write_bytes(b"source")
        destination.write_bytes(b"existing")

        with self.assertRaisesRegex(
            RegularFileSnapshotError,
            "destination already exists",
        ):
            copy_regular_file_bounded(
                source,
                destination,
                max_bytes=1024,
            )

        self.assertEqual(b"existing", destination.read_bytes())

    def test_snapshots_exact_regular_file_bytes(self) -> None:
        _, source = self.fixture()
        source.write_bytes(b"trusted-bytes")

        with snapshot_regular_file(
            source,
            prefix="snapshot-test.",
            max_bytes=1024,
        ) as snapshot:
            self.assertEqual(b"trusted-bytes", snapshot.read_bytes())
            self.assertEqual(0o600, snapshot.stat().st_mode & 0o777)
            source.write_bytes(b"changed")
            self.assertEqual(b"trusted-bytes", snapshot.read_bytes())

        self.assertFalse(snapshot.exists())

    def test_rejects_symlink_and_directory_inputs(self) -> None:
        _, source = self.fixture()
        target = source.parent / "target.bin"
        target.write_bytes(b"target")
        source.symlink_to(target.name)

        with self.assertRaises(RegularFileSnapshotError):
            with snapshot_regular_file(source, prefix="snapshot-test."):
                pass

        source.unlink()
        source.mkdir()
        with self.assertRaises(RegularFileSnapshotError):
            with snapshot_regular_file(source, prefix="snapshot-test."):
                pass

    def test_rejects_input_larger_than_snapshot_limit(self) -> None:
        _, source = self.fixture()
        source.write_bytes(b"12345")

        with self.assertRaisesRegex(
            RegularFileSnapshotError,
            "exceeds snapshot byte limit",
        ):
            with snapshot_regular_file(
                source,
                prefix="snapshot-test.",
                max_bytes=4,
            ):
                pass

    def test_rejects_invalid_snapshot_limit(self) -> None:
        _, source = self.fixture()
        source.write_bytes(b"data")

        for value in (0, -1, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    RegularFileSnapshotError,
                    "positive integer",
                ):
                    with snapshot_regular_file(
                        source,
                        prefix="snapshot-test.",
                        max_bytes=value,
                    ):
                        pass

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW"),
        "platform must provide O_NOFOLLOW",
    )
    def test_source_descriptor_is_opened_without_following_symlinks(self) -> None:
        _, source = self.fixture()
        target = source.parent / "target.bin"
        target.write_bytes(b"target")
        source.symlink_to(target.name)

        with self.assertRaises(RegularFileSnapshotError):
            with snapshot_regular_file(source, prefix="snapshot-test."):
                pass


if __name__ == "__main__":
    unittest.main()
