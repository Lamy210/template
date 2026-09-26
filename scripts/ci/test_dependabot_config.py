from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".github/dependabot.yml"
EXPECTED_SWIFT_DIRECTORIES = (
    "/Tools/VisualDiff",
    "/Tests/AdoptionFixtures/SwiftPM",
)


def swift_update_block(text: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "- package-ecosystem: swift":
            start = index + 1
            break
    if start is None:
        raise AssertionError("Dependabot Swift update block is missing")

    block: list[str] = []
    for line in lines[start:]:
        if line.startswith("  - package-ecosystem:"):
            break
        block.append(line)
    return block


def configured_directories(block: list[str]) -> tuple[str, ...]:
    try:
        start = block.index("    directories:") + 1
    except ValueError as exc:
        raise AssertionError("Swift update block must use directories") from exc

    values: list[str] = []
    for line in block[start:]:
        if line.startswith("    ") and not line.startswith("      "):
            break
        if line.startswith("      - "):
            values.append(line.removeprefix("      - ").strip())
    return tuple(values)


class DependabotConfigTests(unittest.TestCase):
    def test_swift_updates_target_real_package_manifests(self) -> None:
        block = swift_update_block(CONFIG.read_text(encoding="utf-8"))
        directories = configured_directories(block)

        self.assertEqual(EXPECTED_SWIFT_DIRECTORIES, directories)
        self.assertEqual(len(directories), len(set(directories)))

        for directory in directories:
            with self.subTest(directory=directory):
                self.assertTrue(directory.startswith("/"))
                package = ROOT / directory.removeprefix("/") / "Package.swift"
                self.assertTrue(package.is_file(), package)
                self.assertFalse(package.is_symlink(), package)

    def test_swift_updates_do_not_point_at_repository_root_or_failure_fixtures(self) -> None:
        block = swift_update_block(CONFIG.read_text(encoding="utf-8"))
        directories = configured_directories(block)

        self.assertNotIn("    directory: /", block)
        self.assertNotIn("/", directories)
        self.assertTrue(
            all("/scripts/test/fixtures/" not in f"{directory}/" for directory in directories)
        )


if __name__ == "__main__":
    unittest.main()
