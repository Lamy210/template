from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "Tests/AdoptionFixtures/SwiftPM"


class AdoptionFixtureContractTests(unittest.TestCase):
    def test_swiftpm_fixture_has_exact_minimal_structure(self) -> None:
        expected = (
            FIXTURE / "Package.swift",
            FIXTURE / "Sources/AdoptionCore/Counter.swift",
            FIXTURE / "Tests/AdoptionCoreTests/CounterTests.swift",
        )
        for path in expected:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())

    def test_swiftpm_fixture_has_no_external_packages(self) -> None:
        package = (FIXTURE / "Package.swift").read_text(encoding="utf-8")
        self.assertIn('name: "AdoptionCore"', package)
        self.assertIn('.target(name: "AdoptionCore")', package)
        self.assertIn(
            '.testTarget(name: "AdoptionCoreTests", dependencies: ["AdoptionCore"])',
            package,
        )
        self.assertNotIn(".package(", package)

    def test_fixture_exercises_deterministic_code_paths(self) -> None:
        source = (FIXTURE / "Sources/AdoptionCore/Counter.swift").read_text(
            encoding="utf-8"
        )
        tests = (FIXTURE / "Tests/AdoptionCoreTests/CounterTests.swift").read_text(
            encoding="utf-8"
        )
        self.assertIn("func increment", source)
        self.assertIn("func isEven", source)
        self.assertIn("#expect(Counter().increment(41) == 42)", tests)
        self.assertIn("#expect(Counter().isEven(42))", tests)
        self.assertIn("#expect(!Counter().isEven(41))", tests)


if __name__ == "__main__":
    unittest.main()
