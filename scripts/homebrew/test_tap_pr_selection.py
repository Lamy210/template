from __future__ import annotations

import unittest

from scripts.homebrew.tap_pr_selection import select_same_repository_pull_request


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
