from __future__ import annotations

from io import BytesIO
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from scripts.release.capture_release_asset import (
    ReleaseAssetCaptureError,
    capture_release_asset,
)


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class ReleaseAssetCaptureTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        output = Path(temporary_directory.name) / "asset.bin"
        return temporary_directory, output

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
