from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.published_release_assets import verify_published_release_assets
from scripts.release.release_attestation import ExpectedRelease, build_release_attestation


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/verify-published-release-assets.py"
TAG = "v1.2.3"
SOURCE_SHA = "1" * 40
PUBLISHER_SHA = "2" * 40
SOURCE_ARTIFACT_DIGEST = "sha256:" + "a" * 64
ARCHIVE_SHA256 = "sha256:" + "b" * 64


class PublishedReleaseAssetsTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, Path]:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        dmg = root / "MyApp-v1.2.3.dmg"
        checksum = root / f"{dmg.name}.sha256"
        provenance = root / "release-provenance.json"
        dmg.write_bytes(b"published-dmg\n")

        digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
        checksum.write_text(f"{digest}  {dmg.name}\n", encoding="utf-8")
        document = build_release_attestation(
            ExpectedRelease(
                source_repository="example/MyApp",
                source_run_id=100,
                source_run_attempt=1,
                source_sha=SOURCE_SHA,
                tag=TAG,
                source_artifact_id=200,
                source_artifact_digest=SOURCE_ARTIFACT_DIGEST,
                archive_sha256=ARCHIVE_SHA256,
                publisher_run_id=300,
                publisher_sha=PUBLISHER_SHA,
                dmg_path=dmg,
            )
        )
        provenance.write_text(
            json.dumps(document, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return temporary_directory, dmg, checksum, provenance

    def test_accepts_three_mutually_bound_published_assets(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        errors, digest = verify_published_release_assets(
            dmg_path=dmg,
            checksum_path=checksum,
            provenance_path=provenance,
            expected_tag=TAG,
        )
        self.assertEqual([], errors)
        self.assertIsNotNone(digest)
        self.assertEqual(64, len(digest or ""))

    def test_rejects_downloaded_dmg_that_no_longer_matches_checksum_or_provenance(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        dmg.write_bytes(b"replaced-after-publication\n")

        errors, digest = verify_published_release_assets(
            dmg_path=dmg,
            checksum_path=checksum,
            provenance_path=provenance,
            expected_tag=TAG,
        )

        self.assertIsNone(digest)
        self.assertTrue(any("checksum" in error for error in errors))
        self.assertTrue(any("provenance DMG digest" in error for error in errors))

    def test_rejects_provenance_tag_drift(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        document = json.loads(provenance.read_text(encoding="utf-8"))
        document["tag"] = "v1.2.4"
        provenance.write_text(json.dumps(document) + "\n", encoding="utf-8")

        errors, digest = verify_published_release_assets(
            dmg_path=dmg,
            checksum_path=checksum,
            provenance_path=provenance,
            expected_tag=TAG,
        )

        self.assertIsNone(digest)
        self.assertTrue(any("tag" in error for error in errors))

    def test_rejects_symlinked_published_asset(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        target = provenance.with_name("release-provenance.real.json")
        provenance.rename(target)
        provenance.symlink_to(target.name)

        errors, digest = verify_published_release_assets(
            dmg_path=dmg,
            checksum_path=checksum,
            provenance_path=provenance,
            expected_tag=TAG,
        )

        self.assertIsNone(digest)
        self.assertTrue(any("non-symlink" in error for error in errors))

    def test_cli_prints_digest_only_for_bound_assets(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        result = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--dmg",
                str(dmg),
                "--checksum",
                str(checksum),
                "--provenance",
                str(provenance),
                "--tag",
                TAG,
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(result.stdout, r"^[0-9a-f]{64}\n$")


if __name__ == "__main__":
    unittest.main()
