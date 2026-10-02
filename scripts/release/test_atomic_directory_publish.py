from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.release.atomic_directory_publish import (
    AtomicDirectoryPublishError,
    _darwin_publish,
    _linux_publish,
    atomic_publish_directory_noreplace,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/publish-directory-noreplace.py"


class AtomicDirectoryPublishTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "source"
        destination = root / "destination"
        source.mkdir()
        (source / "payload").write_text("trusted\n", encoding="utf-8")
        return temporary_directory, source, destination

    def test_publishes_without_replacing_destination(self) -> None:
        _, source, destination = self.fixture()

        atomic_publish_directory_noreplace(source, destination)

        self.assertFalse(source.exists())
        self.assertEqual(
            "trusted\n",
            (destination / "payload").read_text(encoding="utf-8"),
        )

    def test_rejects_existing_destination_without_modifying_it(self) -> None:
        _, source, destination = self.fixture()
        destination.mkdir()
        (destination / "existing").write_text("keep\n", encoding="utf-8")

        with self.assertRaisesRegex(
            AtomicDirectoryPublishError,
            "destination already exists",
        ):
            atomic_publish_directory_noreplace(source, destination)

        self.assertTrue(source.is_dir())
        self.assertEqual(
            "keep\n",
            (destination / "existing").read_text(encoding="utf-8"),
        )

    def test_rejects_dangling_symlink_destination(self) -> None:
        _, source, destination = self.fixture()
        destination.symlink_to(
            destination.parent / "missing",
            target_is_directory=True,
        )

        with self.assertRaisesRegex(
            AtomicDirectoryPublishError,
            "destination already exists",
        ):
            atomic_publish_directory_noreplace(source, destination)

        self.assertTrue(source.is_dir())
        self.assertTrue(destination.is_symlink())

    def test_rejects_symlink_destination_parent(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        real_parent = root / "real-parent"
        real_parent.mkdir()
        parent_link = root / "parent-link"
        parent_link.symlink_to(real_parent.name, target_is_directory=True)
        source = root / "source"
        source.mkdir()

        with self.assertRaisesRegex(
            AtomicDirectoryPublishError,
            "destination parent must be a real directory",
        ):
            atomic_publish_directory_noreplace(
                source,
                parent_link / "destination",
            )

        self.assertTrue(source.is_dir())
        self.assertFalse((real_parent / "destination").exists())

    def test_native_primitive_does_not_replace_existing_destination(self) -> None:
        _, source, destination = self.fixture()
        destination.mkdir()
        (destination / "existing").write_text("keep\n", encoding="utf-8")

        if sys.platform.startswith("linux"):
            native_publish = _linux_publish
        elif sys.platform == "darwin":
            native_publish = _darwin_publish
        else:
            self.skipTest("native no-replace primitive is not supported on this platform")

        with self.assertRaisesRegex(
            AtomicDirectoryPublishError,
            "destination already exists",
        ):
            native_publish(source, destination)

        self.assertTrue(source.is_dir())
        self.assertEqual(
            "keep\n",
            (destination / "existing").read_text(encoding="utf-8"),
        )

    def test_unsupported_platform_fails_closed(self) -> None:
        _, source, destination = self.fixture()

        with mock.patch(
            "scripts.release.atomic_directory_publish.sys.platform",
            "win32",
        ):
            with self.assertRaisesRegex(
                AtomicDirectoryPublishError,
                "unsupported",
            ):
                atomic_publish_directory_noreplace(source, destination)

        self.assertTrue(source.is_dir())
        self.assertFalse(destination.exists())

    def test_direct_cli_publishes_directory(self) -> None:
        _, source, destination = self.fixture()

        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--source",
                str(source),
                "--destination",
                str(destination),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "trusted\n",
            (destination / "payload").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
