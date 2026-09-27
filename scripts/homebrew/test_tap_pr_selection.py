from __future__ import annotations

import unittest

from scripts.homebrew.tap_pr_selection import (
    normalize_rest_pull_request_pages,
    select_same_repository_pull_request,
)


REPOSITORY = "example/homebrew-tap"
HEAD = "automation/example-v1.2.3"
BASE = "main"
HEAD_SHA = "a" * 40


def pr(
    number: int,
    repository: str,
    *,
    cross_repository: bool,
    head: str = HEAD,
    base: str = BASE,
    head_sha: str = HEAD_SHA,
) -> dict[str, object]:
    owner, name = repository.split("/", 1)
    return {
        "number": number,
        "headRefName": head,
        "baseRefName": base,
        "headRepository": {
            "name": name,
            "nameWithOwner": repository,
        },
        "headRepositoryOwner": {"login": owner},
        "isCrossRepository": cross_repository,
        "headRefOid": head_sha,
    }


def rest_pr(
    number: int,
    repository: str,
    *,
    state: str = "open",
    head: str = HEAD,
    base: str = BASE,
    head_sha: str = HEAD_SHA,
    base_repository: str = REPOSITORY,
) -> dict[str, object]:
    head_owner, head_name = repository.split("/", 1)
    base_owner, base_name = base_repository.split("/", 1)
    return {
        "number": number,
        "state": state,
        "head": {
            "ref": head,
            "sha": head_sha,
            "repo": {
                "full_name": repository,
                "name": head_name,
                "owner": {"login": head_owner},
            },
        },
        "base": {
            "ref": base,
            "repo": {
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
            expected_head=HEAD,
            expected_base=BASE,
            expected_head_sha=HEAD_SHA,
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
            expected_head=HEAD,
            expected_base=BASE,
            expected_head_sha="ABC",
        )
        self.assertIsNone(number)
        self.assertTrue(any("expected head commit" in error for error in errors))

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

        errors, normalized = normalize_rest_pull_request_pages(
            pages,
            expected_repository=REPOSITORY,
        )
        self.assertEqual([], errors)

        errors, number = self.select(normalized)
        self.assertEqual([], errors)
        self.assertEqual(42, number)

    def test_rest_normalization_rejects_duplicate_numbers_across_pages(self) -> None:
        errors, normalized = normalize_rest_pull_request_pages(
            [[rest_pr(42, REPOSITORY)], [rest_pr(42, REPOSITORY)]],
            expected_repository=REPOSITORY,
        )

        self.assertEqual([], normalized[1:])
        self.assertTrue(any("duplicate pull request number" in error for error in errors))

    def test_rest_normalization_rejects_unexpected_base_repository(self) -> None:
        errors, normalized = normalize_rest_pull_request_pages(
            [
                [
                    rest_pr(
                        42,
                        REPOSITORY,
                        base_repository="other/homebrew-tap",
                    )
                ]
            ],
            expected_repository=REPOSITORY,
        )

        self.assertEqual([], normalized)
        self.assertTrue(any("unexpected base repository" in error for error in errors))

    def test_rest_normalization_rejects_closed_pull_request(self) -> None:
        errors, normalized = normalize_rest_pull_request_pages(
            [[rest_pr(42, REPOSITORY, state="closed")]],
            expected_repository=REPOSITORY,
        )

        self.assertEqual([], normalized)
        self.assertTrue(any("is not open" in error for error in errors))

    def test_rest_normalization_requires_paginated_page_arrays(self) -> None:
        errors, normalized = normalize_rest_pull_request_pages(
            [{"number": 42}],
            expected_repository=REPOSITORY,
        )

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
