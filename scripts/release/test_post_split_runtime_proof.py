from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.post_split_runtime_proof import validate_post_split_runtime_proof


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


def artifacts() -> list[dict]:
    return [
        {
            "id": ARTIFACT_ID,
            "name": ARTIFACT_NAME,
            "expired": False,
            "workflow_run": {
                "id": PUBLISHER_RUN_ID,
                "head_sha": PUBLISHER_SHA,
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


def compare() -> dict:
    return {
        "status": "ahead",
        "ahead_by": 7,
        "behind_by": 0,
        "base_commit": {"sha": SOURCE_SHA},
        "merge_base_commit": {"sha": SOURCE_SHA},
    }


class PostSplitRuntimeProofTests(unittest.TestCase):
    def test_accepts_old_source_with_current_default_branch_publisher(self) -> None:
        self.assertEqual(
            [],
            validate_post_split_runtime_proof(
                repository(),
                default_commit(),
                source_run(),
                publisher_run(),
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
                final_default_commit=default_commit(),
            ),
        )

    def test_publisher_release_may_fail_after_secret_free_validation(self) -> None:
        run = publisher_run()
        run["conclusion"] = "failure"
        self.assertEqual(
            [],
            validate_post_split_runtime_proof(
                repository(),
                default_commit(),
                source_run(),
                run,
                artifacts(),
                metadata(),
                "sha256:" + "b" * 64,
                compare(),
            ),
        )

    def test_rejects_source_that_is_not_strict_ancestor(self) -> None:
        relation = compare()
        relation["status"] = "identical"
        relation["ahead_by"] = 0
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), source_run(), publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, relation
        )
        self.assertTrue(any("strict ancestor" in error for error in errors))

    def test_rejects_publisher_not_at_current_default_head(self) -> None:
        head = default_commit()
        head["sha"] = "2" * 40
        errors = validate_post_split_runtime_proof(
            repository(), head, source_run(), publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("current default-branch head" in error for error in errors))

    def test_rejects_default_head_drift_during_collection(self) -> None:
        final_head = default_commit()
        final_head["sha"] = "2" * 40

        errors = validate_post_split_runtime_proof(
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
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), bad_source, publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("source workflow path" in error for error in errors))

        bad_publisher = publisher_run()
        bad_publisher["event"] = "push"
        errors = validate_post_split_runtime_proof(
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
                errors = validate_post_split_runtime_proof(
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

        errors = validate_post_split_runtime_proof(
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
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), run, publisher_run(), artifacts(), metadata(), "sha256:" + "b" * 64, compare()
        )
        self.assertTrue(any("source head repository identity" in error for error in errors))

    def test_rejects_missing_duplicate_expired_or_wrong_artifact(self) -> None:
        cases = [
            [],
            artifacts() + artifacts(),
            [{**artifacts()[0], "expired": True}],
            [{**artifacts()[0], "name": "validated-release-input-wrong"}],
        ]
        for artifact_list in cases:
            with self.subTest(artifact_list=artifact_list):
                errors = validate_post_split_runtime_proof(
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

    def test_rejects_unsigned_archive_digest_drift_from_validated_metadata(self) -> None:
        errors = validate_post_split_runtime_proof(
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
                errors = validate_post_split_runtime_proof(
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
                errors = validate_post_split_runtime_proof(
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
        errors = validate_post_split_runtime_proof(
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

    def test_live_wrapper_is_read_only_and_downloads_exact_publisher_artifact(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        for token in (
            "actions/runs/",
            "/artifacts?per_page=100",
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
