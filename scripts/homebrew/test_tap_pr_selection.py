from __future__ import annotations

import unittest

from scripts.homebrew.tap_pr_selection import (
    normalize_rest_pull_request_pages,
    select_same_repository_pull_request,
)


REPOSITORY = "example/homebrew-tap"
REPOSITORY_ID = 123
FOREIGN_REPOSITORY_ID = 456
HEAD = "automation/example-v1.2.3"
BASE = "main"
HEAD_SHA = "a" * 40


def pr(
    number: int,
    repository: str,
    *,
    repository_id: int | None = None,
    base_repository: str = REPOSITORY,
    base_repository_id: int = REPOSITORY_ID,
    cross_repository: bool,
    head: str = HEAD,
    base: str = BASE,
    head_sha: str = HEAD_SHA,
) -> dict[str, object]:
    owner, name = repository.split("/", 1)
    if repository_id is None:
        repository_id = (
            REPOSITORY_ID
            if repository.lower() == REPOSITORY.lower()
            else FOREIGN_REPOSITORY_ID
        )
    return {
        "number": number,
        "headRefName": head,
        "baseRefName": base,
        "headRepository": {
            "name": name,
            "nameWithOwner": repository,
            "databaseId": repository_id,
        },
        "headRepositoryOwner": {"login": owner},
        "baseRepository": {
            "nameWithOwner": base_repository,
            "databaseId": base_repository_id,
        },
        "isCrossRepository": cross_repository,
        "headRefOid": head_sha,
    }


def rest_pr(
    number: int,
    repository: str,
    *,
    repository_id: int | None = None,
    state: str = "open",
    head: str = HEAD,
    base: str = BASE,
    head_sha: str = HEAD_SHA,
    base_repository: str = REPOSITORY,
    base_repository_id: int = REPOSITORY_ID,
) -> dict[str, object]:
    head_owner, head_name = repository.split("/", 1)
    base_owner, base_name = base_repository.split("/", 1)
    if repository_id is None:
        repository_id = (
            REPOSITORY_ID
            if repository.lower() == REPOSITORY.lower()
            else FOREIGN_REPOSITORY_ID
        )
    return {
        "number": number,
        "state": state,
        "head": {
            "ref": head,
            "sha": head_sha,
            "repo": {
                "id": repository_id,
                "full_name": repository,
                "name": head_name,
                "owner": {"login": head_owner},
            },
        },
        "base": {
            "ref": base,
            "repo": {
                "id": base_repository_id,
                "full_name": base_repository,
                "name": base_name,
                "owner": {"login": base_owner},
            },
        },
    }


class TapPullRequestSelectionTests(unittest.TestCase):
    def select(self, document: object) -> tuple[list[str], int | None]:
        return select_same_repository_pull_request(
            document,
            expected_repository=REPOSITORY,
            expected_repository_id=REPOSITORY_ID,
            expected_head=HEAD,
            expected_base=BASE,
            expected_head_sha=HEAD_SHA,
        )

    def normalize(
        self,
        document: object,
    ) -> tuple[list[str], list[dict[str, object]]]:
        return normalize_rest_pull_request_pages(
            document,
            expected_repository=REPOSITORY,
            expected_repository_id=REPOSITORY_ID,
        )

    def test_selects_one_same_repository_pull_request(self) -> None:
        errors, number = self.select(
            [pr(42, REPOSITORY, cross_repository=False)]
        )
        self.assertEqual([], errors)
        self.assertEqual(42, number)

    def test_selects_same_repository_case_insensitively(self) -> None:
        errors, number = select_same_repository_pull_request(
            [pr(42, "Example/Homebrew-Tap", cross_repository=False)],
            expected_repository="example/homebrew-tap",
            expected_repository_id=REPOSITORY_ID,
            expected_head=HEAD,
            expected_base=BASE,
            expected_head_sha=HEAD_SHA,
        )

        self.assertEqual([], errors)
        self.assertEqual(42, number)

    def test_ignores_same_named_fork_pull_request(self) -> None:
        errors, number = self.select(
            [pr(7, "attacker/homebrew-tap", cross_repository=True, head_sha="b" * 40)]
        )
        self.assertEqual([], errors)
        self.assertIsNone(number)

    def test_prefers_internal_candidate_when_fork_has_same_branch_name(self) -> None:
        errors, number = self.select(
            [
                pr(7, "attacker/homebrew-tap", cross_repository=True),
                pr(42, REPOSITORY, cross_repository=False),
            ]
        )
        self.assertEqual([], errors)
        self.assertEqual(42, number)

    def test_rejects_multiple_internal_candidates(self) -> None:
        errors, number = self.select(
            [
                pr(41, REPOSITORY, cross_repository=False),
                pr(42, REPOSITORY, cross_repository=False),
            ]
        )
        self.assertIsNone(number)
        self.assertTrue(any("more than one" in error for error in errors))

    def test_rejects_query_results_that_drift_from_expected_head_or_base(self) -> None:
        errors, number = self.select(
            [pr(42, REPOSITORY, cross_repository=False, head="other")]
        )
        self.assertIsNone(number)
        self.assertTrue(any("unexpected head branch" in error for error in errors))

        errors, number = self.select(
            [pr(42, REPOSITORY, cross_repository=False, base="develop")]
        )
        self.assertIsNone(number)
        self.assertTrue(any("unexpected base branch" in error for error in errors))

    def test_rejects_internal_pull_request_on_stale_or_raced_head_commit(self) -> None:
        errors, number = self.select(
            [pr(42, REPOSITORY, cross_repository=False, head_sha="b" * 40)]
        )
        self.assertIsNone(number)
        self.assertTrue(any("pushed automation commit" in error for error in errors))

    def test_rejects_invalid_expected_head_commit(self) -> None:
        errors, number = select_same_repository_pull_request(
            [pr(42, REPOSITORY, cross_repository=False)],
            expected_repository=REPOSITORY,
            expected_repository_id=REPOSITORY_ID,
            expected_head=HEAD,
            expected_base=BASE,
            expected_head_sha="ABC",
        )
        self.assertIsNone(number)
        self.assertTrue(any("expected head commit" in error for error in errors))

    def test_rejects_invalid_expected_repository_id(self) -> None:
        for repository_id in (True, 0, -1):
            with self.subTest(repository_id=repository_id):
                errors, number = select_same_repository_pull_request(
                    [pr(42, REPOSITORY, cross_repository=False)],
                    expected_repository=REPOSITORY,
                    expected_repository_id=repository_id,
                    expected_head=HEAD,
                    expected_base=BASE,
                    expected_head_sha=HEAD_SHA,
                )
                self.assertIsNone(number)
                self.assertTrue(
                    any("expected repository id" in error for error in errors)
                )

    def test_rejects_noncanonical_expected_repository(self) -> None:
        for repository in ("../escape", "./repo", "owner/..", "owner/."):
            with self.subTest(repository=repository):
                errors, number = select_same_repository_pull_request(
                    [pr(42, REPOSITORY, cross_repository=False)],
                    expected_repository=repository,
                    expected_repository_id=REPOSITORY_ID,
                    expected_head=HEAD,
                    expected_base=BASE,
                    expected_head_sha=HEAD_SHA,
                )

                self.assertIsNone(number)
                self.assertTrue(
                    any("canonical owner/repo" in error for error in errors),
                    errors,
                )

    def test_rest_normalization_rejects_noncanonical_repository_metadata(self) -> None:
        for field in ("head", "base"):
            with self.subTest(field=field):
                document = rest_pr(42, REPOSITORY)
                repository_document = document[field]["repo"]
                repository_document["full_name"] = "../escape"

                errors, normalized = self.normalize([[document]])

                self.assertEqual([], normalized)
                self.assertTrue(
                    any("repository identity" in error for error in errors),
                    errors,
                )

    def test_rejects_base_repository_id_drift(self) -> None:
        errors, number = self.select(
            [
                pr(
                    42,
                    REPOSITORY,
                    cross_repository=False,
                    base_repository_id=999,
                )
            ]
        )
        self.assertIsNone(number)
        self.assertTrue(
            any("unexpected base repository id" in error for error in errors)
        )

    def test_rejects_same_repository_head_id_drift(self) -> None:
        errors, number = self.select(
            [
                pr(
                    42,
                    REPOSITORY,
                    repository_id=999,
                    cross_repository=False,
                )
            ]
        )
        self.assertIsNone(number)
        self.assertTrue(
            any("same-repository head" in error for error in errors)
        )

    def test_rejects_foreign_name_reusing_trusted_repository_id(self) -> None:
        errors, number = self.select(
            [
                pr(
                    7,
                    "attacker/homebrew-tap",
                    repository_id=REPOSITORY_ID,
                    cross_repository=True,
                )
            ]
        )
        self.assertIsNone(number)
        self.assertTrue(
            any("reuses the expected repository id" in error for error in errors)
        )

    def test_normalizes_paginated_rest_pages_and_selects_internal_candidate(self) -> None:
        pages = [
            [
                rest_pr(
                    7,
                    "attacker/homebrew-tap",
                    head_sha="b" * 40,
                )
            ],
            [rest_pr(42, REPOSITORY)],
        ]

        errors, normalized = self.normalize(pages)
        self.assertEqual([], errors)

        errors, number = self.select(normalized)
        self.assertEqual([], errors)
        self.assertEqual(42, number)
        self.assertEqual(
            REPOSITORY_ID,
            normalized[1]["headRepository"]["databaseId"],
        )
        self.assertEqual(
            REPOSITORY_ID,
            normalized[1]["baseRepository"]["databaseId"],
        )

    def test_rest_normalization_rejects_duplicate_numbers_across_pages(self) -> None:
        errors, normalized = self.normalize(
            [[rest_pr(42, REPOSITORY)], [rest_pr(42, REPOSITORY)]]
        )

        self.assertEqual(1, len(normalized))
        self.assertEqual(42, normalized[0]["number"])
        self.assertTrue(any("duplicate pull request number" in error for error in errors))

    def test_rest_normalization_rejects_unexpected_base_repository(self) -> None:
        errors, normalized = self.normalize(
            [
                [
                    rest_pr(
                        42,
                        REPOSITORY,
                        base_repository="other/homebrew-tap",
                    )
                ]
            ]
        )

        self.assertEqual([], normalized)
        self.assertTrue(any("unexpected base repository" in error for error in errors))

    def test_rest_normalization_rejects_unexpected_base_repository_id(self) -> None:
        errors, normalized = self.normalize(
            [[rest_pr(42, REPOSITORY, base_repository_id=999)]]
        )

        self.assertEqual([], normalized)
        self.assertTrue(
            any("unexpected base repository id" in error for error in errors)
        )

    def test_rest_normalization_rejects_same_repository_head_id_drift(self) -> None:
        errors, normalized = self.normalize(
            [[rest_pr(42, REPOSITORY, repository_id=999)]]
        )

        self.assertEqual([], normalized)
        self.assertTrue(
            any("same-repository head" in error for error in errors)
        )

    def test_rest_normalization_rejects_foreign_name_reusing_trusted_id(self) -> None:
        errors, normalized = self.normalize(
            [
                [
                    rest_pr(
                        7,
                        "attacker/homebrew-tap",
                        repository_id=REPOSITORY_ID,
                    )
                ]
            ]
        )

        self.assertEqual([], normalized)
        self.assertTrue(
            any("reuses the expected repository id" in error for error in errors)
        )

    def test_rest_normalization_rejects_closed_pull_request(self) -> None:
        errors, normalized = self.normalize(
            [[rest_pr(42, REPOSITORY, state="closed")]]
        )

        self.assertEqual([], normalized)
        self.assertTrue(any("is not open" in error for error in errors))

    def test_rest_normalization_requires_paginated_page_arrays(self) -> None:
        errors, normalized = self.normalize([{"number": 42}])

        self.assertEqual([], normalized)
        self.assertTrue(any("page 0 must be a JSON array" in error for error in errors))

    def test_rejects_repository_identity_inconsistency(self) -> None:
        document = pr(42, REPOSITORY, cross_repository=True)
        errors, number = self.select([document])
        self.assertIsNone(number)
        self.assertTrue(any("cross-repository identity" in error for error in errors))

        document = pr(7, "attacker/homebrew-tap", cross_repository=False)
        errors, number = self.select([document])
        self.assertIsNone(number)
        self.assertTrue(any("foreign head repository" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
