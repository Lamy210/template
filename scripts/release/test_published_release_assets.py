from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.release.published_release_assets import (
    MAX_PUBLISHED_METADATA_BYTES,
    verify_published_release_assets,
)
from scripts.release.release_attestation import ExpectedRelease, build_release_attestation


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/verify-published-release-assets.py"
TAG = "v1.2.3"
REPOSITORY = "example/MyApp"
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
                source_repository=REPOSITORY,
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

    def verify(
        self,
        dmg: Path,
        checksum: Path,
        provenance: Path,
        *,
        repository: str = REPOSITORY,
        publisher_sha: str = PUBLISHER_SHA,
    ) -> tuple[list[str], str | None, str | None]:
        return verify_published_release_assets(
            dmg_path=dmg,
            checksum_path=checksum,
            provenance_path=provenance,
            expected_tag=TAG,
            expected_repository=repository,
            expected_publisher_sha=publisher_sha,
        )

    def test_accepts_three_mutually_bound_published_assets(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        errors, digest, source_sha = self.verify(dmg, checksum, provenance)
        self.assertEqual([], errors)
        self.assertIsNotNone(digest)
        self.assertEqual(64, len(digest or ""))
        self.assertEqual(SOURCE_SHA, source_sha)

    def test_coherent_source_replacement_after_snapshot_does_not_change_verified_set(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        trusted_digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
        malicious_dmg = b"coherently-replaced-dmg\n"
        malicious_digest = hashlib.sha256(malicious_dmg).hexdigest()
        malicious_source_sha = "9" * 40
        malicious_provenance = json.loads(
            provenance.read_text(encoding="utf-8")
        )
        malicious_provenance["sourceSHA"] = malicious_source_sha
        malicious_provenance["dmgSha256"] = f"sha256:{malicious_digest}"

        original_read_text = Path.read_text
        mutated = False

        def replace_original_set_then_read(
            path: Path,
            *args,
            **kwargs,
        ) -> str:
            nonlocal mutated
            if not mutated:
                dmg.write_bytes(malicious_dmg)
                checksum.write_text(
                    f"{malicious_digest}  {dmg.name}\n",
                    encoding="utf-8",
                )
                provenance.write_text(
                    json.dumps(malicious_provenance, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                mutated = True
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(
            Path,
            "read_text",
            new=replace_original_set_then_read,
        ):
            errors, digest, source_sha = self.verify(
                dmg,
                checksum,
                provenance,
            )

        self.assertEqual([], errors)
        self.assertEqual(trusted_digest, digest)
        self.assertEqual(SOURCE_SHA, source_sha)
        self.assertEqual(malicious_dmg, dmg.read_bytes())
        self.assertEqual(
            malicious_source_sha,
            json.loads(provenance.read_text(encoding="utf-8"))["sourceSHA"],
        )

    def test_rejects_oversized_published_metadata_before_parsing(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        checksum.write_bytes(b"x" * (MAX_PUBLISHED_METADATA_BYTES + 1))

        errors, digest, source_sha = self.verify(
            dmg,
            checksum,
            provenance,
        )

        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(
            any("snapshot byte limit" in error for error in errors),
            errors,
        )

    def test_rejects_downloaded_dmg_that_no_longer_matches_checksum_or_provenance(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        dmg.write_bytes(b"replaced-after-publication\n")

        errors, digest, source_sha = self.verify(dmg, checksum, provenance)

        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(any("checksum" in error for error in errors))
        self.assertTrue(any("provenance DMG digest" in error for error in errors))

    def test_rejects_provenance_repository_and_publisher_drift(self) -> None:
        _, dmg, checksum, provenance = self.fixture()

        errors, digest, source_sha = self.verify(
            dmg,
            checksum,
            provenance,
            repository="attacker/fork",
        )
        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(any("repository" in error for error in errors))

        errors, digest, source_sha = self.verify(
            dmg,
            checksum,
            provenance,
            publisher_sha="3" * 40,
        )
        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(any("publisher SHA" in error for error in errors))

    def test_rejects_malformed_expected_trust_identity(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        errors, digest, source_sha = self.verify(
            dmg,
            checksum,
            provenance,
            repository="../escape",
            publisher_sha="ABC",
        )

        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(any("owner/repo" in error for error in errors))
        self.assertTrue(any("40 lowercase" in error for error in errors))

    def test_rejects_provenance_tag_drift(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        document = json.loads(provenance.read_text(encoding="utf-8"))
        document["tag"] = "v1.2.4"
        provenance.write_text(json.dumps(document) + "\n", encoding="utf-8")

        errors, digest, source_sha = self.verify(dmg, checksum, provenance)

        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(any("tag" in error for error in errors))

    def test_rejects_symlinked_published_asset(self) -> None:
        _, dmg, checksum, provenance = self.fixture()
        target = provenance.with_name("release-provenance.real.json")
        provenance.rename(target)
        provenance.symlink_to(target.name)

        errors, digest, source_sha = self.verify(dmg, checksum, provenance)

        self.assertIsNone(digest)
        self.assertIsNone(source_sha)
        self.assertTrue(any("non-symlink" in error for error in errors))

    def test_cli_prints_digest_and_exports_verified_source_sha(self) -> None:
        temporary_directory, dmg, checksum, provenance = self.fixture()
        source_sha_output = Path(temporary_directory.name) / "source-sha.txt"
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
                "--repository",
                REPOSITORY,
                "--publisher-sha",
                PUBLISHER_SHA,
                "--source-sha-output",
                str(source_sha_output),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertRegex(result.stdout, r"^[0-9a-f]{64}\n$")
        self.assertEqual(
            SOURCE_SHA + "\n",
            source_sha_output.read_text(encoding="utf-8"),
        )

    def test_cli_refuses_to_overwrite_source_sha_output(self) -> None:
        temporary_directory, dmg, checksum, provenance = self.fixture()
        source_sha_output = Path(temporary_directory.name) / "source-sha.txt"
        source_sha_output.write_text("stale\n", encoding="utf-8")
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
                "--repository",
                REPOSITORY,
                "--publisher-sha",
                PUBLISHER_SHA,
                "--source-sha-output",
                str(source_sha_output),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(1, result.returncode)
        self.assertEqual("stale\n", source_sha_output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
