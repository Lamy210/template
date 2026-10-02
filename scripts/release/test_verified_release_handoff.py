from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.release.release_asset_limits import MAX_RELEASE_METADATA_BYTES
from scripts.release.secure_file_snapshot import RegularFileSnapshotError
from scripts.release.verified_release_handoff import (
    prepare_verified_release_handoff,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/prepare-verified-release-handoff.py"
DMG_NAME = "MyApp-1.2.3.dmg"


def write_payload(root: Path) -> None:
    (root / DMG_NAME).write_bytes(b"stable-dmg\n")
    (root / f"{DMG_NAME}.sha256").write_text(
        "checksum\n",
        encoding="utf-8",
    )
    (root / "release-provenance.json").write_text(
        "{}\n",
        encoding="utf-8",
    )


class VerifiedReleaseHandoffTests(unittest.TestCase):
    def fixture(
        self,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        source = root / "release-output"
        output = root / "verified-upload"
        source.mkdir()
        write_payload(source)
        return temporary_directory, source, output

    def test_prepares_stable_exact_handoff_snapshot(self) -> None:
        _, source, output = self.fixture()

        errors = prepare_verified_release_handoff(
            source,
            output,
            dmg_name=DMG_NAME,
        )

        self.assertEqual([], errors)
        self.assertEqual(
            {
                DMG_NAME,
                f"{DMG_NAME}.sha256",
                "release-provenance.json",
            },
            {entry.name for entry in output.iterdir()},
        )
        self.assertEqual(b"stable-dmg\n", (output / DMG_NAME).read_bytes())
        self.assertEqual(0o700, output.stat().st_mode & 0o777)
        for entry in output.iterdir():
            self.assertEqual(0o400, entry.stat().st_mode & 0o777)

        (source / DMG_NAME).write_bytes(b"changed-after-snapshot\n")
        self.assertEqual(b"stable-dmg\n", (output / DMG_NAME).read_bytes())

    def test_rejects_symlinked_source_entry_without_output(self) -> None:
        _, source, output = self.fixture()
        provenance = source / "release-provenance.json"
        target = source / "real-provenance.json"
        provenance.rename(target)
        provenance.symlink_to(target.name)

        errors = prepare_verified_release_handoff(
            source,
            output,
            dmg_name=DMG_NAME,
        )

        self.assertTrue(any("non-symlink" in error for error in errors), errors)
        self.assertFalse(output.exists())

    def test_rejects_oversized_source_without_output(self) -> None:
        _, source, output = self.fixture()
        with (source / "release-provenance.json").open("r+b") as handle:
            handle.truncate(MAX_RELEASE_METADATA_BYTES + 1)

        errors = prepare_verified_release_handoff(
            source,
            output,
            dmg_name=DMG_NAME,
        )

        self.assertTrue(any("exceeds size limit" in error for error in errors), errors)
        self.assertFalse(output.exists())

    def test_copy_failure_leaves_no_output_or_staging(self) -> None:
        temporary_directory, source, output = self.fixture()
        root = Path(temporary_directory.name)
        call_count = 0

        def fail_second_copy(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RegularFileSnapshotError("simulated copy failure")
            from scripts.release.secure_file_snapshot import (
                copy_regular_file_bounded as real_copy,
            )

            return real_copy(*args, **kwargs)

        with mock.patch(
            "scripts.release.verified_release_handoff.copy_regular_file_bounded",
            side_effect=fail_second_copy,
        ):
            errors = prepare_verified_release_handoff(
                source,
                output,
                dmg_name=DMG_NAME,
            )

        self.assertTrue(any("simulated copy failure" in error for error in errors), errors)
        self.assertFalse(output.exists())
        self.assertFalse(any(root.glob(".verified-upload.*")))

    def test_rejects_existing_or_symlink_output(self) -> None:
        temporary_directory, source, output = self.fixture()
        root = Path(temporary_directory.name)

        output.mkdir()
        errors = prepare_verified_release_handoff(
            source,
            output,
            dmg_name=DMG_NAME,
        )
        self.assertTrue(any("must not already exist" in error for error in errors))

        output.rmdir()
        output.symlink_to(root / "missing", target_is_directory=True)
        errors = prepare_verified_release_handoff(
            source,
            output,
            dmg_name=DMG_NAME,
        )
        self.assertTrue(any("must not already exist" in error for error in errors))
        self.assertTrue(output.is_symlink())

    def test_direct_cli_prepares_handoff(self) -> None:
        _, source, output = self.fixture()

        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--source",
                str(source),
                "--output",
                str(output),
                "--dmg-name",
                DMG_NAME,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"stable-dmg\n", (output / DMG_NAME).read_bytes())


if __name__ == "__main__":
    unittest.main()
