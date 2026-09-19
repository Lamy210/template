from __future__ import annotations

import copy
import unittest

from scripts.release.post_split_runtime_proof import validate_post_split_runtime_proof


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
                compare(),
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
                compare(),
            ),
        )

    def test_rejects_source_that_is_not_strict_ancestor(self) -> None:
        relation = compare()
        relation["status"] = "identical"
        relation["ahead_by"] = 0
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), source_run(), publisher_run(), artifacts(), metadata(), relation
        )
        self.assertTrue(any("strict ancestor" in error for error in errors))

    def test_rejects_publisher_not_at_current_default_head(self) -> None:
        head = default_commit()
        head["sha"] = "2" * 40
        errors = validate_post_split_runtime_proof(
            repository(), head, source_run(), publisher_run(), artifacts(), metadata(), compare()
        )
        self.assertTrue(any("current default-branch head" in error for error in errors))

    def test_rejects_wrong_source_or_publisher_workflow_identity(self) -> None:
        bad_source = source_run()
        bad_source["path"] = ".github/workflows/other.yml"
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), bad_source, publisher_run(), artifacts(), metadata(), compare()
        )
        self.assertTrue(any("source workflow path" in error for error in errors))

        bad_publisher = publisher_run()
        bad_publisher["event"] = "push"
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), source_run(), bad_publisher, artifacts(), metadata(), compare()
        )
        self.assertTrue(any("publisher event" in error for error in errors))

    def test_rejects_repository_identity_drift(self) -> None:
        run = source_run()
        run["head_repository"]["id"] = 999
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), run, publisher_run(), artifacts(), metadata(), compare()
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
                    compare(),
                )
                self.assertTrue(any("validator artifact" in error for error in errors))

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
                    compare(),
                )
                self.assertTrue(any(field in error for error in errors))

    def test_rejects_malformed_integer_identity_instead_of_bool_equality(self) -> None:
        run = source_run()
        run["id"] = True
        errors = validate_post_split_runtime_proof(
            repository(), default_commit(), run, publisher_run(), artifacts(), metadata(), compare()
        )
        self.assertTrue(any("source run id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
