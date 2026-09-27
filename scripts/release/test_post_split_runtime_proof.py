from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from scripts.release.post_split_runtime_proof import validate_post_split_runtime_proof
from scripts.release.runtime_proof_source_artifact import (
    verify_runtime_proof_source_artifact,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_AUDIT = REPO_ROOT / "scripts/release/audit-post-split-runtime-proof.sh"
REPO_ID = 1367784801
REPOSITORY = "example/template"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
PUBLISHER_SHA = "1123456789abcdef0123456789abcdef01234567"
SOURCE_RUN_ID = 101
SOURCE_RUN_ATTEMPT = 1
PUBLISHER_RUN_ID = 202
PUBLISHER_RUN_ATTEMPT = 1
ARTIFACT_ID = 303
ARTIFACT_NAME = (
    f"validated-release-input-{PUBLISHER_RUN_ID}-{PUBLISHER_RUN_ATTEMPT}-"
    f"{SOURCE_RUN_ID}-{SOURCE_RUN_ATTEMPT}"
)


def repository() -> dict:
    return {
        "id": REPO_ID,
        "full_name": REPOSITORY,
        "default_branch": "main",
    }


def default_commit() -> dict:
    return {"sha": PUBLISHER_SHA}


def source_run() -> dict:
    return {
        "id": SOURCE_RUN_ID,
        "run_attempt": SOURCE_RUN_ATTEMPT,
        "name": "Release Build",
        "path": ".github/workflows/release-build.yml",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_sha": SOURCE_SHA,
        "head_branch": "v1.2.3",
        "repository": {"id": REPO_ID, "full_name": REPOSITORY},
        "head_repository": {"id": REPO_ID, "full_name": REPOSITORY},
    }


def publisher_run() -> dict:
    return {
        "id": PUBLISHER_RUN_ID,
        "run_attempt": PUBLISHER_RUN_ATTEMPT,
        "name": "Release Publisher",
        "path": ".github/workflows/release-publisher.yml",
        "event": "workflow_run",
        "status": "completed",
        "conclusion": "failure",
        "head_branch": "main",
        "head_sha": PUBLISHER_SHA,
        "repository": {"id": REPO_ID, "full_name": REPOSITORY},
        "head_repository": {"id": REPO_ID, "full_name": REPOSITORY},
    }


def publisher_jobs() -> list[dict]:
    return [
        {
            "id": 505,
            "name": "Validate release input without secrets",
            "run_id": PUBLISHER_RUN_ID,
            "head_sha": PUBLISHER_SHA,
            "workflow_name": "Release Publisher",
            "head_branch": "main",
            "status": "completed",
            "conclusion": "success",
        }
    ]


def artifacts() -> list[dict]:
    return [
        {
            "id": ARTIFACT_ID,
            "name": ARTIFACT_NAME,
            "expired": False,
            "digest": "sha256:" + "c" * 64,
            "workflow_run": {
                "id": PUBLISHER_RUN_ID,
                "head_sha": PUBLISHER_SHA,
                "repository_id": REPO_ID,
                "head_repository_id": REPO_ID,
            },
        }
    ]


def source_artifacts() -> list[dict]:
    return [
        {
            "id": 404,
            "name": f"unsigned-macos-release-{SOURCE_RUN_ID}-{SOURCE_RUN_ATTEMPT}",
            "expired": False,
            "digest": "sha256:" + "a" * 64,
            "workflow_run": {
                "id": SOURCE_RUN_ID,
                "head_sha": SOURCE_SHA,
                "repository_id": REPO_ID,
                "head_repository_id": REPO_ID,
            },
        }
    ]


def metadata() -> dict:
    return {
        "schemaVersion": 1,
        "sourceRepository": REPOSITORY,
        "sourceRunId": SOURCE_RUN_ID,
        "sourceRunAttempt": SOURCE_RUN_ATTEMPT,
        "sourceSHA": SOURCE_SHA,
        "tag": "v1.2.3",
        "sourceArtifactId": 404,
        "sourceArtifactDigest": "sha256:" + "a" * 64,
        "archiveSha256": "sha256:" + "b" * 64,
        "publisherSHA": PUBLISHER_SHA,
        "publisherRunId": PUBLISHER_RUN_ID,
        "publisherRunAttempt": PUBLISHER_RUN_ATTEMPT,
        "validatedAt": "2026-09-19T00:00:00Z",
        "appBasename": "MyApp.app",
        "bundleId": "com.example.MyApp",
        "version": "1.2.3",
    }


def tag_ref(*, object_type: str = "commit", object_sha: str = SOURCE_SHA) -> dict:
    return {
        "ref": "refs/tags/v1.2.3",
        "object": {
            "type": object_type,
            "sha": object_sha,
        },
    }


def annotated_tag_object(
    sha: str,
    *,
    target_type: str,
    target_sha: str,
) -> dict:
    return {
        "sha": sha,
        "tag": "v1.2.3",
        "object": {
            "type": target_type,
            "sha": target_sha,
        },
    }


def compare() -> dict:
    return {
        "status": "ahead",
        "ahead_by": 7,
        "behind_by": 0,
        "base_commit": {"sha": SOURCE_SHA},
        "merge_base_commit": {"sha": SOURCE_SHA},
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        digest.update(handle.read())
    return "sha256:" + digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write_source_artifact_zip(
    path: Path,
    *,
    app_payload: bytes = b"unsigned-app-archive",
    include_extra: bool = False,
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("release-input/unsigned-macos-app.tar.gz", app_payload)
        archive.writestr("release-input/build-provenance.json", b"{}\n")
        if include_extra:
            archive.writestr("release-input/unexpected.txt", b"unexpected")


def validate_proof(*args: object, **kwargs: object) -> list[str]:
    kwargs.setdefault("source_artifacts", source_artifacts())
    kwargs.setdefault("tag_ref", tag_ref())
    kwargs.setdefault("tag_objects", [])
    kwargs.setdefault("publisher_jobs", publisher_jobs())
    return validate_post_split_runtime_proof(*args, **kwargs)


class RuntimeProofSourceArtifactByteTests(unittest.TestCase):
    def test_accepts_exact_source_artifact_and_inner_archive_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "source-artifact.zip"
            output = root / "source-artifact"
            app_payload = b"exact-unsigned-app-archive"
            write_source_artifact_zip(archive, app_payload=app_payload)

            errors = verify_runtime_proof_source_artifact(
                archive,
                output,
                expected_artifact_digest=sha256_file(archive),
                expected_app_archive_digest=sha256_bytes(app_payload),
            )

            self.assertEqual([], errors)
            self.assertEqual(
                app_payload,
                (output / "release-input/unsigned-macos-app.tar.gz").read_bytes(),
            )

    def test_rejects_source_artifact_zip_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "source-artifact.zip"
            output = root / "source-artifact"
            write_source_artifact_zip(archive)

            errors = verify_runtime_proof_source_artifact(
                archive,
                output,
                expected_artifact_digest="sha256:" + "0" * 64,
                expected_app_archive_digest=sha256_bytes(b"unsigned-app-archive"),
            )

        self.assertTrue(
            any("source Artifact ZIP digest mismatch" in error for error in errors),
            errors,
        )

    def test_rejects_source_unsigned_archive_digest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "source-artifact.zip"
            output = root / "source-artifact"
            write_source_artifact_zip(archive)

            errors = verify_runtime_proof_source_artifact(
                archive,
                output,
                expected_artifact_digest=sha256_file(archive),
                expected_app_archive_digest="sha256:" + "0" * 64,
            )

        self.assertTrue(
            any("source unsigned app archive digest mismatch" in error for error in errors),
            errors,
        )

    def test_rejects_unexpected_source_artifact_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "source-artifact.zip"
            output = root / "source-artifact"
            write_source_artifact_zip(archive, include_extra=True)

            errors = verify_runtime_proof_source_artifact(
                archive,
                output,
                expected_artifact_digest=sha256_file(archive),
                expected_app_archive_digest=sha256_bytes(b"unsigned-app-archive"),
            )

        self.assertTrue(
            any("unexpected files in release artifact" in error for error in errors),
            errors,
        )

    def test_cli_binds_source_artifact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "source-artifact.zip"
            output = root / "source-artifact"
            app_payload = b"cli-unsigned-app-archive"
            write_source_artifact_zip(archive, app_payload=app_payload)

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/release/verify-runtime-proof-source-artifact.py",
                    "--archive",
                    str(archive),
                    "--output",
                    str(output),
                    "--expected-artifact-digest",
                    sha256_file(archive),
                    "--expected-app-archive-digest",
                    sha256_bytes(app_payload),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("source Artifact bytes are bound", result.stdout)


class RuntimeProofLiveTagTests(unittest.TestCase):
    def test_accepts_lightweight_tag_bound_to_source_sha(self) -> None:
        self.assertEqual(
            [],
            validate_proof(
                repository(),
                default_commit(),
                source_run(),
                publisher_run(),
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
            ),
        )

    def test_accepts_annotated_tag_chain_bound_to_source_sha(self) -> None:
        first = "2" * 40
        second = "3" * 40
        self.assertEqual(
            [],
            validate_proof(
                repository(),
                default_commit(),
                source_run(),
                publisher_run(),
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
                tag_ref=tag_ref(object_type="tag", object_sha=first),
                tag_objects=[
                    annotated_tag_object(
                        first,
                        target_type="tag",
                        target_sha=second,
                    ),
                    annotated_tag_object(
                        second,
                        target_type="commit",
                        target_sha=SOURCE_SHA,
                    ),
                ],
            ),
        )

    def test_rejects_live_tag_moved_from_source_sha(self) -> None:
        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "b" * 64,
            compare(),
            tag_ref=tag_ref(object_sha="4" * 40),
        )
        self.assertTrue(
            any("different SHA than the source run" in error for error in errors),
            errors,
        )

    def test_rejects_wrong_tag_ref_name(self) -> None:
        document = tag_ref()
        document["ref"] = "refs/tags/v9.9.9"
        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "b" * 64,
            compare(),
            tag_ref=document,
        )
        self.assertTrue(
            any("tag ref does not match source run tag" in error for error in errors),
            errors,
        )

    def test_rejects_missing_annotated_tag_object(self) -> None:
        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "b" * 64,
            compare(),
            tag_ref=tag_ref(object_type="tag", object_sha="5" * 40),
            tag_objects=[],
        )
        self.assertTrue(
            any("tag object is missing" in error for error in errors),
            errors,
        )

    def test_rejects_annotated_tag_cycle(self) -> None:
        first = "6" * 40
        second = "7" * 40
        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "b" * 64,
            compare(),
            tag_ref=tag_ref(object_type="tag", object_sha=first),
            tag_objects=[
                annotated_tag_object(first, target_type="tag", target_sha=second),
                annotated_tag_object(second, target_type="tag", target_sha=first),
            ],
        )
        self.assertTrue(
            any("contains a cycle" in error for error in errors),
            errors,
        )

    def test_rejects_unconsumed_tag_object_evidence(self) -> None:
        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "b" * 64,
            compare(),
            tag_objects=[
                annotated_tag_object(
                    "8" * 40,
                    target_type="commit",
                    target_sha=SOURCE_SHA,
                )
            ],
        )
        self.assertTrue(
            any("unexpected annotated release tag objects" in error for error in errors),
            errors,
        )


class RuntimeProofPublisherValidationJobTests(unittest.TestCase):
    def test_accepts_exact_successful_validation_job(self) -> None:
        self.assertEqual(
            [],
            validate_proof(
                repository(),
                default_commit(),
                source_run(),
                publisher_run(),
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
            ),
        )

    def test_rejects_missing_duplicate_or_drifted_validation_job(self) -> None:
        base = publisher_jobs()[0]
        cases = (
            ("missing", []),
            ("duplicate", publisher_jobs() + publisher_jobs()),
            ("wrong run", [{**base, "run_id": PUBLISHER_RUN_ID + 1}]),
            ("wrong sha", [{**base, "head_sha": "9" * 40}]),
            ("wrong workflow", [{**base, "workflow_name": "Other Publisher"}]),
            ("wrong branch", [{**base, "head_branch": "release"}]),
            ("not completed", [{**base, "status": "in_progress"}]),
            ("failed", [{**base, "conclusion": "failure"}]),
            ("boolean id", [{**base, "id": True}]),
            ("wrong name", [{**base, "name": "Other validation"}]),
        )
        for label, jobs in cases:
            with self.subTest(label=label):
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    source_run(),
                    publisher_run(),
                    artifacts(),
                    metadata(),
                    "sha256:" + "b" * 64,
                    compare(),
                    publisher_jobs=jobs,
                )
                self.assertTrue(
                    any("publisher validation job" in error for error in errors),
                    errors,
                )


class PostSplitRuntimeProofTests(unittest.TestCase):
    def test_accepts_old_source_with_current_default_branch_publisher(self) -> None:
        self.assertEqual(
            [],
            validate_proof(
                repository(),
                default_commit(),
                source_run(),
                publisher_run(),
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
                source_artifacts=source_artifacts(),
                final_default_commit=default_commit(),
            ),
        )

    def test_publisher_release_may_fail_after_secret_free_validation(self) -> None:
        run = publisher_run()
        run["conclusion"] = "failure"
        self.assertEqual(
            [],
            validate_proof(
                repository(),
                default_commit(),
                source_run(),
                run,
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
                source_artifacts=source_artifacts(),
            ),
        )

    def test_rejects_source_that_is_not_strict_ancestor(self) -> None:
        relation = compare()
        relation["status"] = "identical"
        relation["ahead_by"] = 0
        errors = validate_proof(
            repository(), default_commit(), source_run(), publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, relation
        )
        self.assertTrue(any("strict ancestor" in error for error in errors))

    def test_rejects_publisher_not_at_current_default_head(self) -> None:
        head = default_commit()
        head["sha"] = "2" * 40
        errors = validate_proof(
            repository(), head, source_run(), publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("current default-branch head" in error for error in errors))

    def test_rejects_default_head_drift_during_collection(self) -> None:
        final_head = default_commit()
        final_head["sha"] = "2" * 40

        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "b" * 64,
            compare(),
            final_default_commit=final_head,
        )

        self.assertTrue(
            any(
                "default-branch head changed during runtime proof collection" in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any("final snapshot" in error for error in errors),
            errors,
        )

    def test_rejects_wrong_source_or_publisher_workflow_identity(self) -> None:
        bad_source = source_run()
        bad_source["path"] = ".github/workflows/other.yml"
        errors = validate_proof(
            repository(), default_commit(), bad_source, publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("source workflow path" in error for error in errors))

        bad_publisher = publisher_run()
        bad_publisher["event"] = "push"
        errors = validate_proof(
            repository(), default_commit(), source_run(), bad_publisher, artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("publisher event" in error for error in errors))

    def test_rejects_missing_or_malformed_source_release_tag(self) -> None:
        cases = [None, "main", "v01.2.3", "v1.2.3-rc1"]
        for value in cases:
            with self.subTest(value=value):
                run = source_run()
                if value is None:
                    run.pop("head_branch")
                else:
                    run["head_branch"] = value
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    run,
                    publisher_run(),
                    artifacts(),
                    metadata(),
                    "sha256:" + "b" * 64,
                    compare(),
                )
                self.assertTrue(any("source head_branch" in error for error in errors))

    def test_rejects_metadata_tag_drift_from_source_run_tag(self) -> None:
        document = metadata()
        document["tag"] = "v1.2.4"

        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            document,
            "sha256:" + "b" * 64,
            compare(),
        )

        self.assertTrue(any("tag does not match runtime proof evidence" in error for error in errors))

    def test_rejects_repository_identity_drift(self) -> None:
        run = source_run()
        run["head_repository"]["id"] = 999
        errors = validate_proof(
            repository(), default_commit(), run, publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("source head repository identity" in error for error in errors))

    def test_rejects_live_source_artifact_binding_drift(self) -> None:
        base = source_artifacts()[0]
        cases = (
            ("missing", []),
            ("duplicate", source_artifacts() + source_artifacts()),
            ("expired", [{**base, "expired": True}]),
            ("wrong name", [{**base, "name": "unsigned-macos-release-wrong"}]),
            ("wrong id", [{**base, "id": 405}]),
            ("wrong digest", [{**base, "digest": "sha256:" + "d" * 64}]),
            (
                "wrong run",
                [
                    {
                        **base,
                        "workflow_run": {
                            **base["workflow_run"],
                            "id": SOURCE_RUN_ID + 1,
                        },
                    }
                ],
            ),
            (
                "wrong repository",
                [
                    {
                        **base,
                        "workflow_run": {
                            **base["workflow_run"],
                            "repository_id": REPO_ID + 1,
                        },
                    }
                ],
            ),
        )
        for label, source_artifact_list in cases:
            with self.subTest(label=label):
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    source_run(),
                    publisher_run(),
                    artifacts(),
                    metadata(),
                    "sha256:" + "b" * 64,
                    compare(),
                    source_artifacts=source_artifact_list,
                )
                self.assertTrue(
                    any(
                        "source artifact" in error or "sourceArtifact" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_rejects_missing_duplicate_expired_or_wrong_artifact(self) -> None:
        cases = [
            [],
            artifacts() + artifacts(),
            [{**artifacts()[0], "expired": True}],
            [{**artifacts()[0], "name": "validated-release-input-wrong"}],
        ]
        for artifact_list in cases:
            with self.subTest(artifact_list=artifact_list):
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    source_run(),
                    publisher_run(),
                    artifact_list,
                    metadata(),
                    "sha256:" + "b" * 64,
                    compare(),
                )
                self.assertTrue(any("validator artifact" in error for error in errors))

    def test_rejects_missing_or_malformed_validator_artifact_digest(self) -> None:
        cases = [
            {key: value for key, value in artifacts()[0].items() if key != "digest"},
            {**artifacts()[0], "digest": "bad"},
            {**artifacts()[0], "digest": "sha256:" + "C" * 64},
        ]
        for artifact in cases:
            with self.subTest(artifact=artifact):
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    source_run(),
                    publisher_run(),
                    [artifact],
                    metadata(),
                    "sha256:" + "b" * 64,
                    compare(),
                )
                self.assertTrue(
                    any("validator artifact digest" in error for error in errors),
                    errors,
                )

    def test_rejects_unsigned_archive_digest_drift_from_validated_metadata(self) -> None:
        errors = validate_proof(
            repository(),
            default_commit(),
            source_run(),
            publisher_run(),
            artifacts(),
            metadata(),
            "sha256:" + "c" * 64,
            compare(),
        )

        self.assertTrue(any("unsigned app archive digest" in error for error in errors))

    def test_rejects_metadata_binding_drift(self) -> None:
        fields = {
            "sourceRunId": 999,
            "sourceRunAttempt": 2,
            "sourceSHA": "3" * 40,
            "publisherRunId": 999,
            "publisherRunAttempt": 2,
            "publisherSHA": "4" * 40,
            "sourceRepository": "other/repo",
        }
        for field, value in fields.items():
            with self.subTest(field=field):
                document = metadata()
                document[field] = value
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    source_run(),
                    publisher_run(),
                    artifacts(),
                    document,
                    "sha256:" + "b" * 64,
                    compare(),
                )
                self.assertTrue(any(field in error for error in errors))

    def test_rejects_noncanonical_validator_metadata_schema(self) -> None:
        mutations = (
            ("unexpected field", lambda document: document.__setitem__("unexpected", True)),
            ("missing field", lambda document: document.pop("bundleId")),
            ("tag/version mismatch", lambda document: document.__setitem__("version", "9.9.9")),
            ("bad artifact digest", lambda document: document.__setitem__("sourceArtifactDigest", "bad")),
            ("bad archive digest", lambda document: document.__setitem__("archiveSha256", "sha256:" + "A" * 64)),
            ("bad timestamp", lambda document: document.__setitem__("validatedAt", "2026-09-19T00:00:00+00:00")),
            ("unsafe app basename", lambda document: document.__setitem__("appBasename", "../MyApp.app")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                document = metadata()
                mutate(document)
                errors = validate_proof(
                    repository(),
                    default_commit(),
                    source_run(),
                    publisher_run(),
                    artifacts(),
                    document,
                    "sha256:" + "b" * 64,
                    compare(),
                )
                self.assertTrue(
                    any("validator metadata:" in error for error in errors),
                    errors,
                )

    def test_rejects_malformed_integer_identity_instead_of_bool_equality(self) -> None:
        run = source_run()
        run["id"] = True
        errors = validate_proof(
            repository(), default_commit(), run, publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("source run id" in error for error in errors))

    def test_cli_accepts_paginated_artifact_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixtures = {
                "repository.json": repository(),
                "default-commit.json": default_commit(),
                "final-default-commit.json": default_commit(),
                "source-run.json": source_run(),
                "publisher-run.json": publisher_run(),
                "publisher-jobs.json": [
                    {"total_count": 1, "jobs": publisher_jobs()}
                ],
                "source-artifacts.json": [
                    {"total_count": 1, "artifacts": source_artifacts()}
                ],
                "tag-ref.json": tag_ref(),
                "tag-objects.json": [],
                "artifacts.json": [{"total_count": 1, "artifacts": artifacts()}],
                "metadata.json": metadata(),
                "compare.json": compare(),
            }
            for name, document in fixtures.items():
                (root / name).write_text(json.dumps(document) + "\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/release/audit-post-split-runtime-proof.py",
                    "--repository",
                    str(root / "repository.json"),
                    "--default-commit",
                    str(root / "default-commit.json"),
                    "--final-default-commit",
                    str(root / "final-default-commit.json"),
                    "--source-run",
                    str(root / "source-run.json"),
                    "--publisher-run",
                    str(root / "publisher-run.json"),
                    "--publisher-jobs",
                    str(root / "publisher-jobs.json"),
                    "--source-artifacts",
                    str(root / "source-artifacts.json"),
                    "--tag-ref",
                    str(root / "tag-ref.json"),
                    "--tag-objects",
                    str(root / "tag-objects.json"),
                    "--artifacts",
                    str(root / "artifacts.json"),
                    "--metadata",
                    str(root / "metadata.json"),
                    "--archive-digest",
                    "sha256:" + "b" * 64,
                    "--compare",
                    str(root / "compare.json"),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("post-split runtime proof is valid", result.stdout)

    def test_cli_writes_evidence_only_after_successful_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixtures = {
                "repository.json": repository(),
                "default-commit.json": default_commit(),
                "final-default-commit.json": default_commit(),
                "source-run.json": source_run(),
                "publisher-run.json": publisher_run(),
                "publisher-jobs.json": [
                    {"total_count": 1, "jobs": publisher_jobs()}
                ],
                "source-artifacts.json": [
                    {"total_count": 1, "artifacts": source_artifacts()}
                ],
                "tag-ref.json": tag_ref(),
                "tag-objects.json": [],
                "artifacts.json": [{"total_count": 1, "artifacts": artifacts()}],
                "metadata.json": metadata(),
                "compare.json": compare(),
            }
            for name, document in fixtures.items():
                (root / name).write_text(json.dumps(document) + "\n", encoding="utf-8")

            output = root / "proof.json"
            args = [
                sys.executable,
                "scripts/release/audit-post-split-runtime-proof.py",
                "--repository",
                str(root / "repository.json"),
                "--default-commit",
                str(root / "default-commit.json"),
                "--final-default-commit",
                str(root / "final-default-commit.json"),
                "--source-run",
                str(root / "source-run.json"),
                "--publisher-run",
                str(root / "publisher-run.json"),
                "--publisher-jobs",
                str(root / "publisher-jobs.json"),
                "--source-artifacts",
                str(root / "source-artifacts.json"),
                "--tag-ref",
                str(root / "tag-ref.json"),
                "--tag-objects",
                str(root / "tag-objects.json"),
                "--artifacts",
                str(root / "artifacts.json"),
                "--metadata",
                str(root / "metadata.json"),
                "--archive-digest",
                "sha256:" + "b" * 64,
                "--compare",
                str(root / "compare.json"),
                "--evidence-output",
                str(output),
            ]
            first = subprocess.run(
                args,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, first.returncode, first.stderr)
            document = json.loads(output.read_text(encoding="utf-8"))
            second = subprocess.run(
                args,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(2, second.returncode)
        self.assertIn("already exists", second.stderr)
        self.assertEqual(2, document["schemaVersion"])
        self.assertEqual("sha256:" + "c" * 64, document["publisher"]["validatorArtifactDigest"])
        self.assertEqual("sha256:" + "a" * 64, document["source"]["artifactDigest"])
        self.assertEqual("sha256:" + "b" * 64, document["source"]["archiveDigest"])

    def test_cli_does_not_write_evidence_when_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bad_final = default_commit()
            bad_final["sha"] = "2" * 40
            fixtures = {
                "repository.json": repository(),
                "default-commit.json": default_commit(),
                "final-default-commit.json": bad_final,
                "source-run.json": source_run(),
                "publisher-run.json": publisher_run(),
                "publisher-jobs.json": [
                    {"total_count": 1, "jobs": publisher_jobs()}
                ],
                "source-artifacts.json": [
                    {"total_count": 1, "artifacts": source_artifacts()}
                ],
                "tag-ref.json": tag_ref(),
                "tag-objects.json": [],
                "artifacts.json": [{"total_count": 1, "artifacts": artifacts()}],
                "metadata.json": metadata(),
                "compare.json": compare(),
            }
            for name, document in fixtures.items():
                (root / name).write_text(json.dumps(document) + "\n", encoding="utf-8")

            output = root / "proof.json"
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/release/audit-post-split-runtime-proof.py",
                    "--repository",
                    str(root / "repository.json"),
                    "--default-commit",
                    str(root / "default-commit.json"),
                    "--final-default-commit",
                    str(root / "final-default-commit.json"),
                    "--source-run",
                    str(root / "source-run.json"),
                    "--publisher-run",
                    str(root / "publisher-run.json"),
                    "--publisher-jobs",
                    str(root / "publisher-jobs.json"),
                    "--source-artifacts",
                    str(root / "source-artifacts.json"),
                    "--tag-ref",
                    str(root / "tag-ref.json"),
                    "--tag-objects",
                    str(root / "tag-objects.json"),
                    "--artifacts",
                    str(root / "artifacts.json"),
                    "--metadata",
                    str(root / "metadata.json"),
                    "--archive-digest",
                    "sha256:" + "b" * 64,
                    "--compare",
                    str(root / "compare.json"),
                    "--evidence-output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, result.returncode)
            self.assertFalse(output.exists())

    def test_live_wrapper_rejects_existing_evidence_before_github_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "proof.json"
            output.write_text("{}\n", encoding="utf-8")
            result = subprocess.run(
                [
                    "bash",
                    str(LIVE_AUDIT),
                    "example/disposable",
                    "101",
                    "202",
                    "--evidence-output",
                    str(output),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(2, result.returncode)
        self.assertIn("must not already exist", result.stderr)

    def test_live_wrapper_is_read_only_and_downloads_exact_publisher_artifact(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        for token in (
            "actions/runs/",
            "/attempts/${publisher_run_attempt}/jobs?per_page=100",
            "publisher-jobs.json",
            "--publisher-jobs",
            "/artifacts?per_page=100",
            "source-artifacts.json",
            "/git/ref/tags/",
            "/git/tags/",
            "tag-ref.json",
            "tag-objects.json",
            "--tag-ref",
            "--tag-objects",
            "source-artifact.zip",
            "verify-runtime-proof-source-artifact.py",
            "--expected-artifact-digest",
            "--expected-app-archive-digest",
            "/actions/artifacts/${source_artifact_id}/zip",
            "/actions/artifacts/${artifact_id}/zip",
            "extract-runtime-proof-metadata.py",
            "--app-archive-digest-output",
            "--archive-digest",
            "artifact_digest",
            "compare/",
            "validated-release-input-",
            "audit-post-split-runtime-proof.py",
            "--final-default-commit",
            "final-default-commit.json",
            "--source-artifacts",
            "--evidence-output",
        ):
            with self.subTest(token=token):
                self.assertIn(token, text)
        self.assertNotIn("gh run download", text)
        self.assertEqual(
            2,
            text.count('repos/${repository}/commits/${encoded_default_branch}'),
        )
        self.assertLess(
            text.index('repos/${repository}/compare/${source_sha}...${publisher_sha}'),
            text.index('>"${temp_root}/final-default-commit.json"'),
        )

        for mutation in (
            "--method POST",
            "--method PUT",
            "--method PATCH",
            "--method DELETE",
            "git/refs",
            "rulesets/",
            "/environments/release/deployment-branch-policies/",
        ):
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, text)


if __name__ == "__main__":
    unittest.main()
