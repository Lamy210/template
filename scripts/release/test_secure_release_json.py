from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from scripts.release.release_asset_limits import MAX_RELEASE_METADATA_BYTES
from scripts.release.secure_release_json import (
    SecureReleaseJsonError,
    load_bounded_release_json,
    write_release_json_exclusive,
)


class SecureReleaseJsonTests(unittest.TestCase):
    def test_load_rejects_oversized_and_symlinked_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            oversized = root / "oversized.json"
            with oversized.open("wb") as handle:
                handle.truncate(MAX_RELEASE_METADATA_BYTES + 1)

            with self.assertRaisesRegex(
                SecureReleaseJsonError,
                "snapshot byte limit",
            ):
                load_bounded_release_json(
                    oversized,
                    label="release metadata",
                )

            real = root / "real.json"
            real.write_text('{"ok": true}\n', encoding="utf-8")
            symlink = root / "symlink.json"
            symlink.symlink_to(real.name)
            with self.assertRaisesRegex(
                SecureReleaseJsonError,
                "regular non-symlink file",
            ):
                load_bounded_release_json(
                    symlink,
                    label="release metadata",
                )

    def test_write_creates_mode_0600_canonical_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "metadata.json"

            write_release_json_exclusive(
                path,
                {"z": 1, "a": True},
                label="validated release metadata",
            )

            self.assertEqual(
                {"a": True, "z": 1},
                json.loads(path.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                0o600,
                stat.S_IMODE(path.stat().st_mode),
            )

    def test_write_refuses_existing_file_and_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            existing = root / "existing.json"
            existing.write_text("keep\n", encoding="utf-8")

            with self.assertRaisesRegex(
                SecureReleaseJsonError,
                "already exists",
            ):
                write_release_json_exclusive(
                    existing,
                    {"replace": True},
                    label="validated release metadata",
                )
            self.assertEqual("keep\n", existing.read_text(encoding="utf-8"))

            target = root / "target.json"
            target.write_text("target\n", encoding="utf-8")
            symlink = root / "symlink.json"
            symlink.symlink_to(target.name)
            with self.assertRaisesRegex(
                SecureReleaseJsonError,
                "already exists",
            ):
                write_release_json_exclusive(
                    symlink,
                    {"replace": True},
                    label="validated release metadata",
                )
            self.assertEqual("target\n", target.read_text(encoding="utf-8"))

    def test_write_refuses_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            real_parent = root / "real"
            real_parent.mkdir()
            parent_link = root / "linked"
            parent_link.symlink_to(real_parent.name, target_is_directory=True)

            with self.assertRaisesRegex(
                SecureReleaseJsonError,
                "output parent must be a real directory",
            ):
                write_release_json_exclusive(
                    parent_link / "metadata.json",
                    {"ok": True},
                    label="validated release metadata",
                )
            self.assertFalse((real_parent / "metadata.json").exists())

    def test_write_failure_removes_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "metadata.json"

            with self.assertRaisesRegex(
                SecureReleaseJsonError,
                "unable to write",
            ):
                write_release_json_exclusive(
                    path,
                    {"bad": object()},
                    label="validated release metadata",
                )

            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
