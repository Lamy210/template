from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

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

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform must provide O_NOFOLLOW/O_DIRECTORY",
    )
    def test_bounded_copy_allows_symlinked_destination_ancestor(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source.bin"
        source.write_bytes(b"trusted-copy")
        real_root = root / "real-root"
        destination_parent = real_root / "destination"
        destination_parent.mkdir(parents=True)
        alias_root = root / "alias-root"
        alias_root.symlink_to(real_root, target_is_directory=True)
        destination = alias_root / "destination" / "copy.bin"

        copied = copy_regular_file_bounded(
            source,
            destination,
            max_bytes=1024,
        )

        self.assertEqual(len(b"trusted-copy"), copied)
        self.assertEqual(
            b"trusted-copy",
            (destination_parent / "copy.bin").read_bytes(),
        )

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform must provide O_NOFOLLOW/O_DIRECTORY",
    )
    def test_bounded_copy_rejects_symlinked_destination_parent(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source.bin"
        source.write_bytes(b"trusted-copy")
        real_parent = root / "real-parent"
        real_parent.mkdir()
        destination_parent = root / "destination"
        destination_parent.symlink_to(real_parent, target_is_directory=True)
        destination = destination_parent / "copy.bin"

        with self.assertRaises(RegularFileSnapshotError):
            copy_regular_file_bounded(
                source,
                destination,
                max_bytes=1024,
            )

        self.assertFalse((real_parent / "copy.bin").exists())

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform must provide O_NOFOLLOW/O_DIRECTORY",
    )
    def test_bounded_copy_rejects_destination_parent_symlink_race(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source.bin"
        source.write_bytes(b"trusted-copy")
        destination_parent = root / "destination"
        destination_parent.mkdir()
        outside = root / "outside"
        outside.mkdir()
        destination = destination_parent / "copy.bin"
        real_fstat = os.fstat
        raced = False

        def racing_fstat(descriptor: int):
            nonlocal raced
            metadata = real_fstat(descriptor)
            if not raced and stat.S_ISREG(metadata.st_mode):
                raced = True
                destination_parent.rename(root / "destination.trusted")
                destination_parent.symlink_to(outside, target_is_directory=True)
            return metadata

        with mock.patch(
            "scripts.release.secure_file_snapshot.os.fstat",
            side_effect=racing_fstat,
        ):
            with self.assertRaises(RegularFileSnapshotError):
                copy_regular_file_bounded(
                    source,
                    destination,
                    max_bytes=1024,
                )

        self.assertTrue(raced)
        self.assertFalse((outside / "copy.bin").exists())

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

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform must provide O_NOFOLLOW/O_DIRECTORY",
    )
    def test_snapshot_source_parent_race_never_changes_snapshotted_bytes(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        trusted_parent = root / "trusted"
        trusted_parent.mkdir()
        source = trusted_parent / "source.bin"
        source.write_bytes(b"trusted-bytes")
        outside = root / "outside"
        outside.mkdir()
        (outside / "source.bin").write_bytes(b"untrusted-bytes")
        real_open = os.open
        raced = False

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal raced
            is_source_open = (
                dir_fd is None and Path(path) == source
            ) or (
                dir_fd is not None and path == source.name
            )
            if not raced and is_source_open:
                raced = True
                trusted_parent.rename(root / "trusted.original")
                trusted_parent.symlink_to(outside, target_is_directory=True)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        snapshotted_bytes: bytes | None = None
        with mock.patch(
            "scripts.release.secure_file_snapshot.os.open",
            side_effect=racing_open,
        ):
            try:
                with snapshot_regular_file(
                    source,
                    prefix="snapshot-test.",
                    max_bytes=1024,
                ) as snapshot:
                    snapshotted_bytes = snapshot.read_bytes()
            except RegularFileSnapshotError:
                pass

        self.assertTrue(raced)
        if snapshotted_bytes is not None:
            self.assertEqual(b"trusted-bytes", snapshotted_bytes)

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
