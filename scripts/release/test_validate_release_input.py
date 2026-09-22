from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tarfile
import tempfile
import unittest

from scripts.release.release_input import validate_release_input
from scripts.release.test_release_provenance import SHA, valid_document


PUBLISHER_SHA = "1123456789abcdef0123456789abcdef01234567"
PUBLISHER_RUN_ID = 99887766
PUBLISHER_RUN_ATTEMPT = 4


def create_app_archive(
    path: Path,
    *,
    bundle_id: str = "com.example.MyApp",
    version: str = "1.2.3",
    plist_executable: str = "MyApp",
    symlink_plist: bool = False,
    symlink_executable: bool = False,
) -> str:
    plist = plistlib.dumps(
        {
            "CFBundleIdentifier": bundle_id,
            "CFBundleShortVersionString": version,
            "CFBundleExecutable": plist_executable,
        },
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )
    with tarfile.open(path, "w:gz") as archive:
        for name in (
            "MyApp.app",
            "MyApp.app/Contents",
            "MyApp.app/Contents/MacOS",
        ):
            entry = tarfile.TarInfo(name)
            entry.type = tarfile.DIRTYPE
            entry.mode = 0o755
            archive.addfile(entry)

        if symlink_plist:
            real_info = tarfile.TarInfo("MyApp.app/Contents/RealInfo.plist")
            real_info.size = len(plist)
            real_info.mode = 0o644
            archive.addfile(real_info, io.BytesIO(plist))

            info = tarfile.TarInfo("MyApp.app/Contents/Info.plist")
            info.type = tarfile.SYMTYPE
            info.linkname = "RealInfo.plist"
            info.mode = 0o777
            archive.addfile(info)
        else:
            info = tarfile.TarInfo("MyApp.app/Contents/Info.plist")
            info.size = len(plist)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(plist))

        executable = b"#!/usr/bin/env bash\nexit 0\n"
        if symlink_executable:
            real_binary = tarfile.TarInfo("MyApp.app/Contents/MacOS/RealMyApp")
            real_binary.size = len(executable)
            real_binary.mode = 0o755
            archive.addfile(real_binary, io.BytesIO(executable))

            binary = tarfile.TarInfo("MyApp.app/Contents/MacOS/MyApp")
            binary.type = tarfile.SYMTYPE
            binary.linkname = "RealMyApp"
            binary.mode = 0o777
            archive.addfile(binary)
        else:
            binary = tarfile.TarInfo("MyApp.app/Contents/MacOS/MyApp")
            binary.size = len(executable)
            binary.mode = 0o755
            archive.addfile(binary, io.BytesIO(executable))

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def source_metadata() -> dict:
    return {
        "schemaVersion": 1,
        "repository": "example/MyApp",
        "workflowId": 4242,
        "workflowPath": ".github/workflows/release-build.yml",
        "runId": 123456789,
        "runAttempt": 2,
        "sourceSHA": SHA,
        "sourceTag": "v1.2.3",
        "artifactId": 7001,
        "artifactName": "unsigned-macos-release-123456789-2",
        "artifactDigest": "sha256:" + "b" * 64,
    }


def provenance(archive_digest: str) -> dict:
    document = valid_document()
    document["archiveSha256"] = archive_digest
    return document


class ReleaseInputValidationTests(unittest.TestCase):
    def validate_fixture(
        self,
        *,
        provenance_mutator=None,
        metadata_mutator=None,
        bundle_id: str = "com.example.MyApp",
        app_version: str = "1.2.3",
        plist_executable: str = "MyApp",
        symlink_plist: bool = False,
        symlink_executable: bool = False,
        resolved_tag_sha: str = SHA,
        source_is_ancestor: bool = True,
        publisher_run_id: int = PUBLISHER_RUN_ID,
        publisher_run_attempt: int = PUBLISHER_RUN_ATTEMPT,
    ):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "unsigned-macos-app.tar.gz"
            archive_digest = create_app_archive(
                archive,
                bundle_id=bundle_id,
                version=app_version,
                plist_executable=plist_executable,
                symlink_plist=symlink_plist,
                symlink_executable=symlink_executable,
            )
            provenance_document = provenance(archive_digest)
            metadata = source_metadata()
            if provenance_mutator is not None:
                provenance_mutator(provenance_document)
            if metadata_mutator is not None:
                metadata_mutator(metadata)

            errors, validated = validate_release_input(
                provenance_document=provenance_document,
                source_metadata=metadata,
                archive_path=archive,
                expected_repository="example/MyApp",
                expected_workflow_path=".github/workflows/release-build.yml",
                expected_app_basename="MyApp.app",
                expected_bundle_id="com.example.MyApp",
                resolved_tag_sha=resolved_tag_sha,
                source_is_ancestor=source_is_ancestor,
                publisher_sha=PUBLISHER_SHA,
                publisher_run_id=publisher_run_id,
                publisher_run_attempt=publisher_run_attempt,
                release_scripts_root=Path(__file__).resolve().parent,
            )
            return errors, validated

    def test_cli_help_executes_from_repository_root(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "scripts/release/validate-release-input.py", "--help"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Validate release input before privileged signing", result.stdout)

    def test_valid_release_input_returns_validator_owned_metadata(self) -> None:
        errors, validated = self.validate_fixture()
        self.assertEqual([], errors)
        assert validated is not None
        self.assertEqual(123456789, validated["sourceRunId"])
        self.assertEqual(2, validated["sourceRunAttempt"])
        self.assertEqual("v1.2.3", validated["tag"])
        self.assertEqual(SHA, validated["sourceSHA"])
        self.assertEqual(PUBLISHER_SHA, validated["publisherSHA"])
        self.assertEqual(PUBLISHER_RUN_ID, validated["publisherRunId"])
        self.assertEqual(PUBLISHER_RUN_ATTEMPT, validated["publisherRunAttempt"])
        self.assertRegex(
            validated["validatedAt"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )
        self.assertEqual("com.example.MyApp", validated["bundleId"])

    def test_rejects_provenance_run_identity_mismatch(self) -> None:
        errors, _ = self.validate_fixture(
            provenance_mutator=lambda document: document.__setitem__("sourceRunAttempt", 3)
        )
        self.assertTrue(any("sourceRunAttempt" in error for error in errors))

    def test_rejects_provenance_release_identity_drift_from_trusted_source_tag(self) -> None:
        def mutate(document: dict) -> None:
            document["tag"] = "v1.2.4"
            document["sourceRef"] = "refs/tags/v1.2.4"
            document["version"] = "1.2.4"

        errors, _ = self.validate_fixture(provenance_mutator=mutate)

        self.assertTrue(
            any("tag" in error or "sourceRef" in error or "version" in error for error in errors)
        )

    def test_rejects_resolved_tag_sha_mismatch(self) -> None:
        errors, _ = self.validate_fixture(resolved_tag_sha="2" * 40)
        self.assertTrue(any("resolved tag SHA" in error for error in errors))

    def test_rejects_source_not_reachable_from_default_branch(self) -> None:
        errors, _ = self.validate_fixture(source_is_ancestor=False)
        self.assertTrue(any("default branch" in error for error in errors))

    def test_rejects_archive_digest_mismatch(self) -> None:
        errors, _ = self.validate_fixture(
            provenance_mutator=lambda document: document.__setitem__(
                "archiveSha256", "sha256:" + "0" * 64
            )
        )
        self.assertTrue(any("archive SHA-256" in error for error in errors))

    def test_rejects_bundle_identifier_mismatch(self) -> None:
        errors, _ = self.validate_fixture(bundle_id="com.attacker.Other")
        self.assertTrue(any("bundle identifier" in error for error in errors))

    def test_rejects_application_version_mismatch(self) -> None:
        errors, _ = self.validate_fixture(app_version="9.9.9")
        self.assertTrue(any("bundle version" in error for error in errors))

    def test_rejects_symlinked_info_plist(self) -> None:
        errors, _ = self.validate_fixture(symlink_plist=True)
        self.assertTrue(any("Info.plist is missing or unsafe" in error for error in errors))

    def test_rejects_unsafe_cf_bundle_executable(self) -> None:
        errors, _ = self.validate_fixture(plist_executable="../MyApp")
        self.assertTrue(any("CFBundleExecutable" in error for error in errors))

    def test_rejects_symlinked_cf_bundle_executable(self) -> None:
        errors, _ = self.validate_fixture(symlink_executable=True)
        self.assertTrue(
            any(
                "bundle executable contract failed" in error and "symbolic link" in error
                for error in errors
            )
        )

    def test_rejects_source_metadata_artifact_name_mismatch(self) -> None:
        errors, _ = self.validate_fixture(
            metadata_mutator=lambda metadata: metadata.__setitem__("artifactName", "other")
        )
        self.assertTrue(any("artifactName" in error for error in errors))

    def test_rejects_noncanonical_source_metadata(self) -> None:
        errors, _ = self.validate_fixture(
            metadata_mutator=lambda metadata: metadata.__setitem__("extra", True)
        )
        self.assertTrue(any("source metadata" in error for error in errors))

    def test_rejects_invalid_publisher_sha(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "unsigned-macos-app.tar.gz"
            archive_digest = create_app_archive(archive)
            errors, _ = validate_release_input(
                provenance_document=provenance(archive_digest),
                source_metadata=source_metadata(),
                archive_path=archive,
                expected_repository="example/MyApp",
                expected_workflow_path=".github/workflows/release-build.yml",
                expected_app_basename="MyApp.app",
                expected_bundle_id="com.example.MyApp",
                resolved_tag_sha=SHA,
                source_is_ancestor=True,
                publisher_sha="INVALID",
                publisher_run_id=PUBLISHER_RUN_ID,
                publisher_run_attempt=PUBLISHER_RUN_ATTEMPT,
                release_scripts_root=Path(__file__).resolve().parent,
            )
        self.assertTrue(any("publisher SHA" in error for error in errors))

    def test_rejects_invalid_publisher_run_identity(self) -> None:
        errors, _ = self.validate_fixture(publisher_run_id=True, publisher_run_attempt=0)
        self.assertTrue(any("publisher run ID" in error for error in errors))
        self.assertTrue(any("publisher run attempt" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
