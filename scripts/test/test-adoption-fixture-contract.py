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

    def test_xcode_fixture_has_committed_shared_scheme_and_sources(self) -> None:
        fixture = ROOT / "Tests/AdoptionFixtures/Xcode"
        expected = (
            fixture / "AdoptionApp.xcodeproj/project.pbxproj",
            fixture
            / "AdoptionApp.xcodeproj/xcshareddata/xcschemes/AdoptionApp.xcscheme",
            fixture / "Sources/AdoptionApp/main.swift",
            fixture / "Sources/AdoptionCore/Counter.swift",
            fixture / "Tests/AdoptionCoreTests/CounterTests.swift",
        )
        for path in expected:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())

    def test_xcode_fixture_is_secret_free_and_unsigned(self) -> None:
        fixture = ROOT / "Tests/AdoptionFixtures/Xcode"
        project = (fixture / "AdoptionApp.xcodeproj/project.pbxproj").read_text(
            encoding="utf-8"
        )
        scheme = (
            fixture
            / "AdoptionApp.xcodeproj/xcshareddata/xcschemes/AdoptionApp.xcscheme"
        ).read_text(encoding="utf-8")
        self.assertIn('productType = "com.apple.product-type.application";', project)
        self.assertIn('productType = "com.apple.product-type.bundle.unit-test";', project)
        self.assertIn("CODE_SIGNING_ALLOWED = NO;", project)
        self.assertIn('BlueprintName = "AdoptionCoreTests"', scheme)
        self.assertNotIn("DevelopmentTeam", project)
        self.assertNotIn("PROVISIONING_PROFILE", project)

    def test_xcode_fixture_has_deterministic_visual_capture_contract(self) -> None:
        fixture = ROOT / "Tests/AdoptionFixtures/Xcode"
        manifest = fixture / "VisualRegression/visual-regression.json"
        baseline = fixture / "VisualBaselines/adoption-counter.png"
        tests = fixture / "Tests/AdoptionCoreTests/CounterTests.swift"

        for path in (manifest, baseline):
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())

        self.assertEqual(b"\\x89PNG\\r\\n\\x1a\\n", baseline.read_bytes()[:8])
        manifest_text = manifest.read_text(encoding="utf-8")
        self.assertIn('"profile": "adoption-macos-app-xcode-26.6"', manifest_text)
        self.assertIn(
            '"current": "artifacts/visual/current/adoption-counter.png"',
            manifest_text,
        )
        self.assertIn(
            '"expected": "Tests/AdoptionFixtures/Xcode/VisualBaselines/adoption-counter.png"',
            manifest_text,
        )

        test_source = tests.read_text(encoding="utf-8")
        self.assertIn('environment["GITHUB_WORKSPACE"]', test_source)
        self.assertIn("artifacts/visual/current", test_source)
        self.assertIn("adoption-counter.png", test_source)

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
