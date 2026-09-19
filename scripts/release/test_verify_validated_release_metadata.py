from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.release.validated_release_metadata import ExpectedValidatedRelease, verify_validated_release_metadata


SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
PUBLISHER_SHA = "1123456789abcdef0123456789abcdef01234567"
PUBLISHER_RUN_ID = 99887766
PUBLISHER_RUN_ATTEMPT = 4
SOURCE_ARTIFACT_ID = 7001
ARTIFACT_DIGEST = "sha256:" + "b" * 64


def expected(archive_digest: str) -> ExpectedValidatedRelease:
    return ExpectedValidatedRelease(
        source_repository="example/MyApp",
        source_run_id=123456789,
        source_run_attempt=2,
        source_artifact_id=SOURCE_ARTIFACT_ID,
        source_artifact_digest=ARTIFACT_DIGEST,
        source_sha=SOURCE_SHA,
        source_tag="v1.2.3",
        source_version="1.2.3",
        publisher_sha=PUBLISHER_SHA,
        publisher_run_id=PUBLISHER_RUN_ID,
        publisher_run_attempt=PUBLISHER_RUN_ATTEMPT,
        archive_sha256=archive_digest,
        app_basename="MyApp.app",
        bundle_id="com.example.MyApp",
    )


def metadata(archive_digest: str) -> dict:
    return {
        "schemaVersion": 1,
        "sourceRepository": "example/MyApp",
        "sourceRunId": 123456789,
        "sourceRunAttempt": 2,
        "sourceSHA": SOURCE_SHA,
        "tag": "v1.2.3",
        "sourceArtifactId": SOURCE_ARTIFACT_ID,
        "sourceArtifactDigest": ARTIFACT_DIGEST,
        "archiveSha256": archive_digest,
        "publisherSHA": PUBLISHER_SHA,
        "publisherRunId": PUBLISHER_RUN_ID,
        "publisherRunAttempt": PUBLISHER_RUN_ATTEMPT,
        "validatedAt": "2026-09-19T07:11:12Z",
        "appBasename": "MyApp.app",
        "bundleId": "com.example.MyApp",
        "version": "1.2.3",
    }


class ValidatedReleaseMetadataTests(unittest.TestCase):
    def fixture(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        archive = Path(temporary_directory.name) / "unsigned-macos-app.tar.gz"
        payload = b"validated release archive\n"
        archive.write_bytes(payload)
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        return archive, digest

    def test_valid_metadata_and_archive_have_no_errors(self) -> None:
        archive, digest = self.fixture()
        self.assertEqual(
            [],
            verify_validated_release_metadata(metadata(digest), archive, expected(digest)),
        )

    def test_rejects_non_object_metadata(self) -> None:
        archive, digest = self.fixture()
        self.assertTrue(verify_validated_release_metadata([], archive, expected(digest)))

    def test_rejects_unknown_or_missing_fields(self) -> None:
        archive, digest = self.fixture()
        document = metadata(digest)
        document["unexpected"] = True
        document.pop("publisherSHA")
        errors = verify_validated_release_metadata(document, archive, expected(digest))
        self.assertTrue(any("unexpected fields" in error for error in errors))
        self.assertTrue(any("missing fields" in error for error in errors))

    def test_rejects_malformed_validation_timestamp(self) -> None:
        archive, digest = self.fixture()
        for value in (
            "",
            "2026-09-19T07:11:12+00:00",
            "2026-09-19T07:11Z",
            "2026-13-19T07:11:12Z",
            True,
        ):
            with self.subTest(value=value):
                document = metadata(digest)
                document["validatedAt"] = value
                errors = verify_validated_release_metadata(document, archive, expected(digest))
                self.assertTrue(any("validatedAt" in error for error in errors))

    def test_rejects_bool_for_integer_identity(self) -> None:
        archive, digest = self.fixture()
        document = metadata(digest)
        document["sourceRunId"] = True
        document["publisherRunAttempt"] = True
        errors = verify_validated_release_metadata(document, archive, expected(digest))
        self.assertTrue(any("sourceRunId" in error for error in errors))
        self.assertTrue(any("publisherRunAttempt" in error for error in errors))

    def test_rejects_metadata_source_identity_drift(self) -> None:
        archive, digest = self.fixture()
        mutations = (
            ("sourceRepository", "attacker/fork"),
            ("sourceRunAttempt", 3),
            ("sourceSHA", "2" * 40),
            ("tag", "v1.2.4"),
            ("version", "1.2.4"),
            ("publisherSHA", "3" * 40),
            ("publisherRunId", PUBLISHER_RUN_ID + 1),
            ("publisherRunAttempt", PUBLISHER_RUN_ATTEMPT + 1),
            ("appBasename", "Other.app"),
            ("bundleId", "com.attacker.Other"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = metadata(digest)
                document[key] = value
                errors = verify_validated_release_metadata(document, archive, expected(digest))
                self.assertTrue(any(key in error or "expected" in error for error in errors))

    def test_rejects_source_artifact_identity_drift(self) -> None:
        archive, digest = self.fixture()
        mutations = (
            ("sourceArtifactId", SOURCE_ARTIFACT_ID + 1),
            ("sourceArtifactDigest", "sha256:" + "c" * 64),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = metadata(digest)
                document[key] = value
                errors = verify_validated_release_metadata(document, archive, expected(digest))
                self.assertTrue(any(key in error or "expected" in error for error in errors))

    def test_rejects_tag_version_inconsistency(self) -> None:
        archive, digest = self.fixture()
        document = metadata(digest)
        document["version"] = "1.2.4"
        expected_value = copy.deepcopy(expected(digest))
        expected_value = ExpectedValidatedRelease(**{**expected_value.__dict__, "source_version": "1.2.4"})
        errors = verify_validated_release_metadata(document, archive, expected_value)
        self.assertTrue(any("tag/version" in error for error in errors))

    def test_rejects_semver_tag_with_leading_zeroes_even_when_expected_matches(self) -> None:
        archive, digest = self.fixture()
        for tag in ("v01.2.3", "v1.02.3", "v1.2.03"):
            with self.subTest(tag=tag):
                version = tag[1:]
                document = metadata(digest)
                document["tag"] = tag
                document["version"] = version
                expected_value = expected(digest)
                expected_value = ExpectedValidatedRelease(
                    **{
                        **expected_value.__dict__,
                        "source_tag": tag,
                        "source_version": version,
                    }
                )

                errors = verify_validated_release_metadata(document, archive, expected_value)

                self.assertTrue(
                    any("stable SemVer" in error for error in errors),
                    f"privileged metadata accepted leading-zero tag: {tag}",
                )

    def test_rejects_archive_digest_mismatch_even_if_metadata_matches_expected_text(self) -> None:
        archive, digest = self.fixture()
        wrong_digest = "sha256:" + "0" * 64
        errors = verify_validated_release_metadata(
            metadata(wrong_digest),
            archive,
            expected(wrong_digest),
        )
        self.assertTrue(any("actual archive SHA-256" in error for error in errors))

    def test_rejects_malformed_digests_and_shas(self) -> None:
        archive, digest = self.fixture()
        document = metadata(digest)
        document["sourceArtifactDigest"] = "bad"
        document["publisherSHA"] = "BAD"
        errors = verify_validated_release_metadata(document, archive, expected(digest))
        self.assertTrue(any("sourceArtifactDigest" in error for error in errors))
        self.assertTrue(any("publisherSHA" in error for error in errors))

    def test_rejects_unsafe_app_basename(self) -> None:
        archive, digest = self.fixture()
        document = metadata(digest)
        document["appBasename"] = "../MyApp.app"
        errors = verify_validated_release_metadata(document, archive, expected(digest))
        self.assertTrue(any("appBasename" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
