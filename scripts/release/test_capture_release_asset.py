from __future__ import annotations

from io import BytesIO
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.release.capture_release_asset import (
    ReleaseAssetCaptureError,
    capture_release_asset,
)


ROOT = Path(__file__).resolve().parents[2]


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class ReleaseAssetCaptureTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        output = Path(temporary_directory.name) / "asset.bin"
        return temporary_directory, output

    def test_direct_cli_is_package_safe_from_repository_root(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/release/capture_release_asset.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_captures_exact_size_and_digest(self) -> None:
        _, output = self.fixture()
        payload = b"trusted-release-asset"

        capture_release_asset(
            BytesIO(payload),
            output,
            expected_size=len(payload),
            expected_digest=digest(payload),
        )

        self.assertEqual(payload, output.read_bytes())
        self.assertEqual(0o600, output.stat().st_mode & 0o777)

    def test_rejects_stream_larger_than_expected_and_removes_partial(self) -> None:
        _, output = self.fixture()
        payload = b"123456"

        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "exceeded expected size",
        ):
            capture_release_asset(
                BytesIO(payload),
                output,
                expected_size=5,
                expected_digest=digest(payload[:5]),
            )

        self.assertFalse(output.exists())

    def test_rejects_stream_smaller_than_expected_and_removes_partial(self) -> None:
        _, output = self.fixture()
        payload = b"1234"

        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "size mismatch",
        ):
            capture_release_asset(
                BytesIO(payload),
                output,
                expected_size=5,
                expected_digest=digest(payload),
            )

        self.assertFalse(output.exists())

    def test_rejects_digest_mismatch_and_removes_partial(self) -> None:
        _, output = self.fixture()
        payload = b"trusted"

        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "digest mismatch",
        ):
            capture_release_asset(
                BytesIO(payload),
                output,
                expected_size=len(payload),
                expected_digest=digest(b"different"),
            )

        self.assertFalse(output.exists())

    def test_rejects_existing_or_symlink_output(self) -> None:
        temporary_directory, output = self.fixture()
        root = Path(temporary_directory.name)

        output.write_bytes(b"existing")
        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "already exists",
        ):
            capture_release_asset(
                BytesIO(b"x"),
                output,
                expected_size=1,
                expected_digest=digest(b"x"),
            )
        self.assertEqual(b"existing", output.read_bytes())

        output.unlink()
        output.symlink_to(root / "missing")
        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "already exists",
        ):
            capture_release_asset(
                BytesIO(b"x"),
                output,
                expected_size=1,
                expected_digest=digest(b"x"),
            )
        self.assertTrue(output.is_symlink())

    def test_rejects_symlink_output_parent(self) -> None:
        temporary_directory, _ = self.fixture()
        root = Path(temporary_directory.name)
        real_parent = root / "real"
        real_parent.mkdir()
        parent_link = root / "link"
        parent_link.symlink_to(real_parent.name, target_is_directory=True)
        output = parent_link / "asset.bin"

        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "output parent must be a real directory",
        ):
            capture_release_asset(
                BytesIO(b"x"),
                output,
                expected_size=1,
                expected_digest=digest(b"x"),
            )

        self.assertFalse((real_parent / "asset.bin").exists())

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform must provide O_NOFOLLOW/O_DIRECTORY",
    )
    def test_rejects_output_parent_real_directory_race(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        output_parent = root / "output"
        output_parent.mkdir()
        output = output_parent / "asset.bin"
        original_parent = root / "output.original"
        payload = b"trusted-release-asset"
        real_open = os.open
        raced = False

        def racing_open(path, flags, mode=0o777, *, dir_fd=None):
            nonlocal raced
            is_output_open = (
                dir_fd is None and Path(path) == output
            ) or (
                dir_fd is not None
                and path == output.name
                and bool(flags & os.O_CREAT)
            )
            if not raced and is_output_open:
                raced = True
                output_parent.rename(original_parent)
                output_parent.mkdir()
            return real_open(path, flags, mode, dir_fd=dir_fd)

        with mock.patch(
            "scripts.release.capture_release_asset.os.open",
            side_effect=racing_open,
        ):
            with self.assertRaises(ReleaseAssetCaptureError):
                capture_release_asset(
                    BytesIO(payload),
                    output,
                    expected_size=len(payload),
                    expected_digest=digest(payload),
                )

        self.assertTrue(raced)
        self.assertFalse((output_parent / output.name).exists())
        self.assertFalse((original_parent / output.name).exists())

    @unittest.skipUnless(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY"),
        "platform must provide O_NOFOLLOW/O_DIRECTORY",
    )
    def test_cleanup_uses_anchored_parent_after_path_replacement(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        output_parent = root / "output"
        output_parent.mkdir()
        output = output_parent / "asset.bin"
        original_parent = root / "output.original"
        sentinel = b"replacement-sentinel"
        payload = b"trusted-release-asset"

        class RacingStream(BytesIO):
            def __init__(self, initial_bytes: bytes) -> None:
                super().__init__(initial_bytes)
                self.raced = False

            def read(self, size: int = -1) -> bytes:
                if not self.raced:
                    self.raced = True
                    output_parent.rename(original_parent)
                    output_parent.mkdir()
                    (output_parent / output.name).write_bytes(sentinel)
                return super().read(size)

        stream = RacingStream(payload)
        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "digest mismatch",
        ):
            capture_release_asset(
                stream,
                output,
                expected_size=len(payload),
                expected_digest=digest(b"different"),
            )

        self.assertTrue(stream.raced)
        self.assertEqual(sentinel, (output_parent / output.name).read_bytes())
        self.assertFalse((original_parent / output.name).exists())

    def test_rejects_invalid_expected_contract(self) -> None:
        _, output = self.fixture()
        for size in (0, -1, True):
            with self.subTest(size=size):
                with self.assertRaisesRegex(
                    ReleaseAssetCaptureError,
                    "positive integer",
                ):
                    capture_release_asset(
                        BytesIO(b"x"),
                        output,
                        expected_size=size,
                        expected_digest=digest(b"x"),
                    )

        with self.assertRaisesRegex(
            ReleaseAssetCaptureError,
            "sha256",
        ):
            capture_release_asset(
                BytesIO(b"x"),
                output,
                expected_size=1,
                expected_digest="sha256:BAD",
            )


if __name__ == "__main__":
    unittest.main()
