from __future__ import annotations

import unittest

from scripts.common.repository_name import is_canonical_repository_name


class RepositoryNameTests(unittest.TestCase):
    def test_accepts_canonical_github_repository_names(self) -> None:
        for value in (
            "owner/repo",
            "Lamy210/template",
            "example/homebrew-tap",
            "owner.name/repo_name",
        ):
            with self.subTest(value=value):
                self.assertTrue(is_canonical_repository_name(value))

    def test_rejects_unsafe_or_malformed_repository_names(self) -> None:
        for value in (
            None,
            "",
            "repo",
            "/repo",
            "owner/",
            "owner/repo/extra",
            "../escape",
            "./repo",
            "owner/..",
            "owner/.",
            "owner\\repo",
            "owner/repo\nother",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_canonical_repository_name(value))


if __name__ == "__main__":
    unittest.main()
