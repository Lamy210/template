from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.release_attestation import (
    ExpectedRelease,
    build_release_attestation,
    validate_release_attestation,
    verify_release_attestation,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_CLI = REPO_ROOT / "scripts/release/verify-release-provenance.py"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
PUBLISHER_SHA = "1123456789abcdef0123456789abcdef01234567"
SOURCE_ARTIFACT_DIGEST = "sha256:" + "a" * 64
ARCHIVE_SHA256 = "sha256:" + "b" * 64


def expected_release(dmg_path: Path) -> ExpectedRelease:
    return ExpectedRelease(
        source_repository="example/MyApp",
        source_run_id=123456789,
        source_run_attempt=2,
        source_sha=SOURCE_SHA,
        tag="v1.2.3",
        source_artifact_id=7001,
        source_artifact_digest=SOURCE_ARTIFACT_DIGEST,
        archive_sha256=ARCHIVE_SHA256,
        publisher_run_id=99887766,
        publisher_sha=PUBLISHER_SHA,
        app_basename="MyApp.app",
        bundle_id="com.example.MyApp",
        dmg_path=dmg_path,
    )


class ReleaseAttestationTests(unittest.TestCase):
    def test_build_hashes_final_dmg_and_emits_closed_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dmg = Path(temporary_directory) / "MyApp-v1.2.3.dmg"
            payload = b"signed-notarized-dmg-fixture\n"
            dmg.write_bytes(payload)

            document = build_release_attestation(expected_release(dmg))

            self.assertEqual([], validate_release_attestation(document))
            self.assertEqual(2, document["schemaVersion"])
            self.assertEqual(
                "sha256:" + hashlib.sha256(payload).hexdigest(),
                document["dmgSha256"],
            )
            self.assertEqual(
                {
                    "schemaVersion",
                    "sourceRepository",
                    "sourceRunId",
                    "sourceRunAttempt",
                    "sourceSHA",
                    "tag",
                    "sourceArtifactId",
                    "sourceArtifactDigest",
                    "archiveSha256",
                    "publisherRunId",
                    "publisherSHA",
                    "appBasename",
                    "bundleId",
                    "dmgSha256",
                },
                set(document),
            )
            self.assertNotIn("publisherRunAttempt", document)
            self.assertNotIn("validatedAt", document)

    def test_rejects_unknown_missing_and_malformed_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dmg = Path(temporary_directory) / "MyApp-v1.2.3.dmg"
            dmg.write_bytes(b"fixture")
            valid = build_release_attestation(expected_release(dmg))

        mutations = []
        unknown = dict(valid)
        unknown["futureTrustFlag"] = True
        mutations.append(unknown)

        missing = dict(valid)
        missing.pop("sourceSHA")
        mutations.append(missing)

        bool_id = dict(valid)
        bool_id["publisherRunId"] = True
        mutations.append(bool_id)

        bad_sha = dict(valid)
        bad_sha["publisherSHA"] = "A" * 40
        mutations.append(bad_sha)

        bad_digest = dict(valid)
        bad_digest["sourceArtifactDigest"] = "sha512:" + "a" * 64
        mutations.append(bad_digest)

        bad_tag = dict(valid)
        bad_tag["tag"] = "v01.2.3"
        mutations.append(bad_tag)

        bad_repository = dict(valid)
        bad_repository["sourceRepository"] = "../repo"
        mutations.append(bad_repository)

        bad_app_basename = dict(valid)
        bad_app_basename["appBasename"] = "../MyApp.app"
        mutations.append(bad_app_basename)

        empty_bundle_id = dict(valid)
        empty_bundle_id["bundleId"] = ""
        mutations.append(empty_bundle_id)

        for document in mutations:
            with self.subTest(document=document):
                self.assertTrue(validate_release_attestation(document))

    def test_verifier_binds_release_identity_and_exact_dmg(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dmg = Path(temporary_directory) / "MyApp-v1.2.3.dmg"
            dmg.write_bytes(b"signed-notarized-dmg-fixture\n")
            expected = expected_release(dmg)
            document = build_release_attestation(expected)

            self.assertEqual([], verify_release_attestation(document, expected))

            drifted = dict(document)
            drifted["sourceRunAttempt"] = 3
            identity_errors = verify_release_attestation(drifted, expected)
            self.assertTrue(any("sourceRunAttempt" in error for error in identity_errors))

            app_drifted = dict(document)
            app_drifted["appBasename"] = "Other.app"
            app_errors = verify_release_attestation(app_drifted, expected)
            self.assertTrue(any("appBasename" in error for error in app_errors))

            bundle_drifted = dict(document)
            bundle_drifted["bundleId"] = "com.attacker.Other"
            bundle_errors = verify_release_attestation(bundle_drifted, expected)
            self.assertTrue(any("bundleId" in error for error in bundle_errors))

            dmg.write_bytes(b"tampered-final-dmg\n")
            digest_errors = verify_release_attestation(document, expected)
            self.assertTrue(any("exact release DMG" in error for error in digest_errors))

    def test_verifier_cli_rejects_tampered_final_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dmg = root / "MyApp-v1.2.3.dmg"
            metadata = root / "release-provenance.json"
            dmg.write_bytes(b"stable-final-dmg\n")
            document = build_release_attestation(expected_release(dmg))
            document["publisherSHA"] = "2" * 40
            metadata.write_text(
                json.dumps(document, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(VERIFY_CLI),
                    "--metadata",
                    str(metadata),
                    "--dmg",
                    str(dmg),
                    "--repository",
                    "example/MyApp",
                    "--source-run-id",
                    "123456789",
                    "--source-run-attempt",
                    "2",
                    "--source-sha",
                    SOURCE_SHA,
                    "--source-tag",
                    "v1.2.3",
                    "--source-artifact-id",
                    "7001",
                    "--source-artifact-digest",
                    SOURCE_ARTIFACT_DIGEST,
                    "--archive-sha256",
                    ARCHIVE_SHA256,
                    "--publisher-run-id",
                    "99887766",
                    "--publisher-sha",
                    PUBLISHER_SHA,
                    "--app-basename",
                    "MyApp.app",
                    "--bundle-id",
                    "com.example.MyApp",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("publisherSHA", result.stdout)

    def test_writer_is_deterministic_for_same_release_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dmg = root / "MyApp-v1.2.3.dmg"
            first = root / "first.json"
            second = root / "second.json"
            dmg.write_bytes(b"stable-final-dmg\n")

            base = [
                sys.executable,
                str(REPO_ROOT / "scripts/release/write-release-provenance.py"),
                "--source-repository",
                "example/MyApp",
                "--source-run-id",
                "123456789",
                "--source-run-attempt",
                "2",
                "--source-sha",
                SOURCE_SHA,
                "--tag",
                "v1.2.3",
                "--source-artifact-id",
                "7001",
                "--source-artifact-digest",
                SOURCE_ARTIFACT_DIGEST,
                "--archive-sha256",
                ARCHIVE_SHA256,
                "--publisher-run-id",
                "99887766",
                "--publisher-sha",
                PUBLISHER_SHA,
                "--app-basename",
                "MyApp.app",
                "--bundle-id",
                "com.example.MyApp",
                "--dmg-path",
                str(dmg),
            ]
            subprocess.run(base + ["--output", str(first)], cwd=REPO_ROOT, check=True)
            subprocess.run(base + ["--output", str(second)], cwd=REPO_ROOT, check=True)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            document = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual([], validate_release_attestation(document))
            self.assertTrue(first.read_text(encoding="utf-8").endswith("\n"))


if __name__ == "__main__":
    unittest.main()
