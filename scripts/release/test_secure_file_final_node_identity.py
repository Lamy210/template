from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    copy_regular_file_bounded,
)


@unittest.skipUnless(
    hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
    "platform must provide O_NOFOLLOW/O_DIRECTORY",
)
class SecureFileFinalNodeIdentityTests(unittest.TestCase):
    def test_bounded_copy_rejects_source_file_real_node_race(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source.bin"
        source.write_bytes(b"trusted-copy")
        original_source = root / "source.original"
        replacement_bytes = b"untrusted-copy"
        destination_parent = root / "destination"
        destination_parent.mkdir()
        destination = destination_parent / "copy.bin"
        real_open = os.open
        raced = False

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal raced
            if (
                not raced
                and dir_fd is not None
                and path == source.name
                and not flags & os.O_DIRECTORY
            ):
                raced = True
                source.rename(original_source)
                source.write_bytes(replacement_bytes)
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch(
            "scripts.release.secure_file_snapshot.os.open",
            side_effect=racing_open,
        ):
            with self.assertRaises(RegularFileSnapshotError):
                copy_regular_file_bounded(
                    source,
                    destination,
                    max_bytes=1024,
                )

        self.assertTrue(raced)
        self.assertFalse(destination.exists())
        self.assertEqual(b"trusted-copy", original_source.read_bytes())
        self.assertEqual(replacement_bytes, source.read_bytes())

    def test_bounded_copy_rejects_destination_parent_real_node_race(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source.bin"
        source.write_bytes(b"trusted-copy")
        destination_ancestor = root / "destination-root"
        destination_parent = destination_ancestor / "destination"
        destination_parent.mkdir(parents=True)
        destination = destination_parent / "copy.bin"
        original_parent = destination_ancestor / "destination.original"
        real_open = os.open
        raced = False

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal raced
            if (
                not raced
                and dir_fd is not None
                and path == destination_parent.name
                and flags & os.O_DIRECTORY
            ):
                raced = True
                destination_parent.rename(original_parent)
                destination_parent.mkdir()
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch(
            "scripts.release.secure_file_snapshot.os.open",
            side_effect=racing_open,
        ):
            with self.assertRaises(RegularFileSnapshotError):
                copy_regular_file_bounded(
                    source,
                    destination,
                    max_bytes=1024,
                )

        self.assertTrue(raced)
        self.assertFalse((destination_parent / "copy.bin").exists())
        self.assertFalse((original_parent / "copy.bin").exists())


if __name__ == "__main__":
    unittest.main()
