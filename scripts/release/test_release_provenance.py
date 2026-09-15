from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.release_provenance import ExpectedBuild, validate_build_provenance


SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "a" * 64
REPO_ROOT = Path(__file__).resolve().parents[2]


def valid_document() -> dict:
    return {
        "schemaVersion": 1,
        "repository": "example/MyApp",
        "sourceWorkflowName": "Release Build",
        "sourceWorkflowPath": ".github/workflows/release-build.yml",
        "sourceRunId": 123456789,
        "sourceRunAttempt": 2,
        "sourceEvent": "push",
        "sourceSHA": SHA,
        "sourceRef": "refs/tags/v1.2.3",
        "tag": "v1.2.3",
        "artifactName": "unsigned-macos-release-123456789-2",
        "archiveName": "unsigned-macos-app.tar.gz",
        "archiveSha256": DIGEST,
        "appBasename": "MyApp.app",
        "bundleId": "com.example.MyApp",
        "version": "1.2.3",
    }


def expected_build() -> ExpectedBuild:
    return ExpectedBuild(
        repository="example/MyApp",
        workflow_name="Release Build",
        workflow_path=".github/workflows/release-build.yml",
        run_id=123456789,
        run_attempt=2,
        source_event="push",
        source_sha=SHA,
        source_ref="refs/tags/v1.2.3",
        tag="v1.2.3",
        artifact_name="unsigned-macos-release-123456789-2",
        archive_name="unsigned-macos-app.tar.gz",
        app_basename="MyApp.app",
        bundle_id="com.example.MyApp",
        version="1.2.3",
    )


class ReleaseProvenanceTests(unittest.TestCase):
    def test_valid_document_has_no_errors(self) -> None:
        self.assertEqual([], validate_build_provenance(valid_document(), expected_build()))

    def test_rejects_non_object_document(self) -> None:
        self.assertTrue(validate_build_provenance([], expected_build()))

    def test_rejects_unknown_field(self) -> None:
        document = valid_document()
        document["futureTrustFlag"] = True
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("unexpected fields" in error for error in errors))

    def test_rejects_missing_field(self) -> None:
        document = valid_document()
        document.pop("sourceSHA")
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("missing fields" in error for error in errors))

    def test_rejects_boolean_run_id(self) -> None:
        document = valid_document()
        document["sourceRunId"] = True
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("sourceRunId" in error for error in errors))

    def test_rejects_zero_run_attempt(self) -> None:
        document = valid_document()
        document["sourceRunAttempt"] = 0
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("sourceRunAttempt" in error for error in errors))

    def test_rejects_uppercase_or_short_source_sha(self) -> None:
        for value in ("A" * 40, "a" * 39):
            with self.subTest(value=value):
                document = valid_document()
                document["sourceSHA"] = value
                errors = validate_build_provenance(document, expected_build())
                self.assertTrue(any("sourceSHA" in error for error in errors))

    def test_rejects_malformed_archive_digest(self) -> None:
        for value in ("a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63):
            with self.subTest(value=value):
                document = valid_document()
                document["archiveSha256"] = value
                errors = validate_build_provenance(document, expected_build())
                self.assertTrue(any("archiveSha256" in error for error in errors))

    def test_rejects_non_semver_tag(self) -> None:
        document = valid_document()
        document["tag"] = "v1.2.3-beta.1"
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("tag" in error for error in errors))

    def test_rejects_tag_ref_version_mismatch(self) -> None:
        mutations = (
            ("sourceRef", "refs/tags/v1.2.4"),
            ("version", "1.2.4"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = valid_document()
                document[key] = value
                expected = copy.deepcopy(expected_build())
                errors = validate_build_provenance(document, expected)
                self.assertTrue(any("tag/ref/version" in error or key in error for error in errors))

    def test_rejects_wrong_repository_or_workflow_identity(self) -> None:
        mutations = (
            ("repository", "attacker/fork"),
            ("sourceWorkflowName", "Other Workflow"),
            ("sourceWorkflowPath", ".github/workflows/other.yml"),
            ("sourceEvent", "workflow_dispatch"),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = valid_document()
                document[key] = value
                errors = validate_build_provenance(document, expected_build())
                self.assertTrue(any(key in error for error in errors))

    def test_rejects_wrong_run_identity(self) -> None:
        document = valid_document()
        document["sourceRunAttempt"] = 3
        document["artifactName"] = "unsigned-macos-release-123456789-3"
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("sourceRunAttempt" in error for error in errors))

    def test_rejects_unsafe_basenames(self) -> None:
        mutations = (
            ("archiveName", "../unsigned-macos-app.tar.gz"),
            ("appBasename", "nested/MyApp.app"),
            ("appBasename", "MyApp"),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                document = valid_document()
                document[key] = value
                errors = validate_build_provenance(document, expected_build())
                self.assertTrue(any(key in error for error in errors))

    def test_rejects_artifact_name_not_bound_to_run_attempt(self) -> None:
        document = valid_document()
        document["artifactName"] = "unsigned-macos-release-123456789-1"
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("artifactName" in error for error in errors))

    def test_rejects_empty_bundle_id(self) -> None:
        document = valid_document()
        document["bundleId"] = ""
        errors = validate_build_provenance(document, expected_build())
        self.assertTrue(any("bundleId" in error for error in errors))


class BuildProvenanceWriterTests(unittest.TestCase):
    def test_writer_hashes_archive_and_emits_valid_canonical_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "unsigned-macos-app.tar.gz"
            output = root / "build-provenance.json"
            payload = b"deterministic release archive fixture\n"
            archive.write_bytes(payload)

            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/release/write-build-provenance.py"),
                    "--repository",
                    "example/MyApp",
                    "--workflow-name",
                    "Release Build",
                    "--workflow-path",
                    ".github/workflows/release-build.yml",
                    "--run-id",
                    "123456789",
                    "--run-attempt",
                    "2",
                    "--source-sha",
                    SHA,
                    "--tag",
                    "v1.2.3",
                    "--archive-path",
                    str(archive),
                    "--app-basename",
                    "MyApp.app",
                    "--bundle-id",
                    "com.example.MyApp",
                    "--output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                check=True,
            )

            document = json.loads(output.read_text(encoding="utf-8"))
            expected_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
            self.assertEqual(expected_digest, document["archiveSha256"])
            self.assertEqual("refs/tags/v1.2.3", document["sourceRef"])
            self.assertEqual("1.2.3", document["version"])
            self.assertEqual("unsigned-macos-release-123456789-2", document["artifactName"])
            self.assertEqual([], validate_build_provenance(document, expected_build()))

            serialized = output.read_text(encoding="utf-8")
            self.assertTrue(serialized.endswith("\n"))
            self.assertLess(serialized.index('"appBasename"'), serialized.index('"artifactName"'))


if __name__ == "__main__":
    unittest.main()
