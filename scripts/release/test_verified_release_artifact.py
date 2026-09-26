from __future__ import annotations

import unittest

from scripts.release.verified_release_artifact import (
    canonical_verified_release_artifact_name,
    verify_verified_release_artifact,
)


ARTIFACT_DIGEST = "sha256:" + "a" * 64
PUBLISHER_RUN_ID = 99887766
PUBLISHER_RUN_ATTEMPT = 4
PUBLISHER_SHA = "c" * 40
REPOSITORY_ID = 1367784801
ARTIFACT_ID = 7002


def artifact_name(attempt: int = PUBLISHER_RUN_ATTEMPT) -> str:
    return canonical_verified_release_artifact_name(PUBLISHER_RUN_ID, attempt)


def artifact_metadata(*, name: str | None = None) -> dict[str, object]:
    return {
        "id": ARTIFACT_ID,
        "name": name or artifact_name(),
        "expired": False,
        "digest": ARTIFACT_DIGEST,
        "workflow_run": {
            "id": PUBLISHER_RUN_ID,
            "repository_id": REPOSITORY_ID,
            "head_repository_id": REPOSITORY_ID,
            "head_sha": PUBLISHER_SHA,
        },
    }


class VerifiedReleaseArtifactTests(unittest.TestCase):
    def verify(self, document: object, *, name: str | None = None) -> list[str]:
        return verify_verified_release_artifact(
            artifact_metadata=document,
            artifact_id=ARTIFACT_ID,
            artifact_name=name or artifact_name(),
            artifact_digest=ARTIFACT_DIGEST,
            publisher_run_id=PUBLISHER_RUN_ID,
            publisher_run_attempt=PUBLISHER_RUN_ATTEMPT,
            publisher_sha=PUBLISHER_SHA,
            repository_id=REPOSITORY_ID,
        )

    def test_accepts_exact_current_publisher_attempt_artifact(self) -> None:
        self.assertEqual([], self.verify(artifact_metadata()))

    def test_rejects_previous_attempt_name(self) -> None:
        previous = artifact_name(PUBLISHER_RUN_ATTEMPT - 1)
        errors = self.verify(artifact_metadata(name=previous), name=previous)
        self.assertTrue(any("canonical" in error or "publisher" in error for error in errors))

    def test_rejects_identity_digest_expiration_and_run_drift(self) -> None:
        mutations = (
            ("id", ARTIFACT_ID + 1),
            ("digest", "sha256:" + "b" * 64),
            ("expired", True),
            ("workflow_run", {"id": PUBLISHER_RUN_ID + 1}),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = artifact_metadata()
                document[key] = value
                self.assertTrue(self.verify(document))

    def test_binds_repository_and_publisher_sha(self) -> None:
        for key, value in (
            ("repository_id", REPOSITORY_ID + 1),
            ("head_repository_id", REPOSITORY_ID + 1),
            ("head_sha", "d" * 40),
        ):
            with self.subTest(key=key):
                document = artifact_metadata()
                assert isinstance(document["workflow_run"], dict)
                document["workflow_run"][key] = value
                self.assertTrue(self.verify(document))

    def test_rejects_malformed_expected_values(self) -> None:
        errors = verify_verified_release_artifact(
            artifact_metadata=artifact_metadata(),
            artifact_id=True,
            artifact_name="",
            artifact_digest="sha512:" + "a" * 64,
            publisher_run_id=0,
            publisher_run_attempt=False,
            publisher_sha="C" * 40,
            repository_id=0,
        )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
