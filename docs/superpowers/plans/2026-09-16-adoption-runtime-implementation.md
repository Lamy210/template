# Adoption Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the profile contract works in real adopter-like SwiftPM and macOS Xcode projects on GitHub-hosted runners, including Coverage, E2E, and Visual execution.

**Architecture:** Add tiny deterministic fixtures under `Tests/AdoptionFixtures` and a specialized read-only workflow. Ubuntu prepare jobs run the production profile resolver/classifier; macOS jobs consume the normalized contract when calling the existing reusable Swift/E2E/Visual workflows. Fixture bootstrap/baselines remain isolated from trusted production baseline publication.

**Tech Stack:** Swift 6 / SwiftPM, SwiftUI, XCTest/XCUITest, Xcode 26.6, Python 3, GitHub Actions, existing reusable workflows and VisualDiff tooling.

**Spec:** `docs/superpowers/specs/2026-09-16-test-profiles-adoption-design.md`

## Global Constraints

- Begin only after the Test Profiles PR is merged to `main` and its post-merge CI is green.
- Adoption workflows use read-only permissions and no secrets.
- No `pull_request_target`.
- Fixtures use no external packages, network access, TCC-only permissions, or release credentials.
- Coverage adoption uses explicit bootstrap when no trusted main coverage baseline exists.
- Visual adoption uses the committed Git fixture baseline and never publishes a trusted rolling production baseline.
- Xcode fixture project, source, tests, and scheme are committed; CI does not install a project generator.
- The specialized adoption workflow is not a Ruleset-required check in this phase.

---

### Task 1: Add the SwiftPM adopter fixture

**Files:**
- Create: `Tests/AdoptionFixtures/SwiftPM/Package.swift`
- Create: `Tests/AdoptionFixtures/SwiftPM/Sources/AdoptionCore/Counter.swift`
- Create: `Tests/AdoptionFixtures/SwiftPM/Tests/AdoptionCoreTests/CounterTests.swift`

**Interfaces:**
- Package/product/target: `AdoptionCore`
- Test target: `AdoptionCoreTests`
- Provides deterministic executable lines for coverage export.

- [ ] **Step 1: Create `Package.swift`**

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AdoptionCore",
    platforms: [.macOS(.v15)],
    products: [.library(name: "AdoptionCore", targets: ["AdoptionCore"])],
    targets: [
        .target(name: "AdoptionCore"),
        .testTarget(name: "AdoptionCoreTests", dependencies: ["AdoptionCore"]),
    ]
)
```

- [ ] **Step 2: Add deterministic source and tests**

`Counter.swift`:

```swift
public struct Counter: Sendable {
    public init() {}

    public func increment(_ value: Int) -> Int {
        value + 1
    }

    public func isEven(_ value: Int) -> Bool {
        value.isMultiple(of: 2)
    }
}
```

`CounterTests.swift`:

```swift
import Testing
@testable import AdoptionCore

@Test func incrementAddsOne() {
    #expect(Counter().increment(41) == 42)
}

@Test func parityIsDeterministic() {
    #expect(Counter().isEven(42))
    #expect(!Counter().isEven(41))
}
```

- [ ] **Step 3: Run fixture tests with and without coverage**

```bash
swift test --package-path Tests/AdoptionFixtures/SwiftPM
swift test --package-path Tests/AdoptionFixtures/SwiftPM --enable-code-coverage
```

Expected: PASS; the coverage run emits a valid codecov path.

- [ ] **Step 4: Commit**

```bash
git add Tests/AdoptionFixtures/SwiftPM
git commit -m "test(adoption): add SwiftPM fixture"
```

---

### Task 2: Add the deterministic macOS Xcode adopter fixture

**Files:**
- Create: `Tests/AdoptionFixtures/MacOSApp/MacOSAdoption.xcodeproj/project.pbxproj`
- Create: `Tests/AdoptionFixtures/MacOSApp/MacOSAdoption.xcodeproj/xcshareddata/xcschemes/MacOSAdoption.xcscheme`
- Create: `Tests/AdoptionFixtures/MacOSApp/App/MacOSAdoptionApp.swift`
- Create: `Tests/AdoptionFixtures/MacOSApp/App/ContentView.swift`
- Create: `Tests/AdoptionFixtures/MacOSApp/UnitTests/MacOSAdoptionTests.swift`
- Create: `Tests/AdoptionFixtures/MacOSApp/UITests/MacOSAdoptionUITests.swift`

**Interfaces:**
- Project: `MacOSAdoption.xcodeproj`
- Shared scheme: `MacOSAdoption`
- App target/bundle ID: `MacOSAdoption` / `dev.schnee.template.adoption`
- Unit target: `MacOSAdoptionTests`
- UI target/bundle ID: `MacOSAdoptionUITests` / `dev.schnee.template.adoption.uitests`
- Deployment target: macOS 15.0

- [ ] **Step 1: Create and commit one minimal Xcode 26.6 project**

Create the project with the exact names above and a shared scheme whose Test action includes both Unit and UI targets. Commit only shared project data: no `xcuserdata`, signing team, cloud capability, external package, or generated user state. The Debug configuration must build/test on a GitHub-hosted macOS runner without production signing credentials.

- [ ] **Step 2: Add deterministic SwiftUI app source**

`ContentView.swift`:

```swift
import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack(spacing: 12) {
            Text("Template Adoption")
                .font(.title2)
                .accessibilityIdentifier("adoption-title")
            Text("fixture-v1")
                .accessibilityIdentifier("adoption-version")
        }
        .frame(width: 360, height: 220)
    }
}
```

`MacOSAdoptionApp.swift`:

```swift
import SwiftUI

@main
struct MacOSAdoptionApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .defaultSize(width: 360, height: 220)
    }
}
```

- [ ] **Step 3: Add Unit and UI tests**

Unit test:

```swift
import Testing
@testable import MacOSAdoption

@Test func fixtureIdentityIsStable() {
    #expect("fixture-v1" == "fixture-v1")
}
```

UI test:

```swift
import Foundation
import XCTest

final class MacOSAdoptionUITests: XCTestCase {
    func testDeterministicWindowCapture() throws {
        let app = XCUIApplication()
        app.launchEnvironment["TZ"] = "UTC"
        app.launch()
        XCTAssertTrue(app.staticTexts["adoption-title"].waitForExistence(timeout: 10))

        guard let outputDirectory = ProcessInfo.processInfo.environment["VISUAL_OUTPUT_DIR"] else {
            XCTFail("VISUAL_OUTPUT_DIR is required by the adoption E2E contract")
            return
        }

        let output = URL(fileURLWithPath: outputDirectory)
            .appendingPathComponent("main-window.png")
        try XCUIScreen.main.screenshot().pngRepresentation.write(to: output)
    }
}
```

- [ ] **Step 4: Validate the project on the canonical toolchain**

```bash
DEVELOPER_DIR=/Applications/Xcode_26.6.app/Contents/Developer \
  xcodebuild -project Tests/AdoptionFixtures/MacOSApp/MacOSAdoption.xcodeproj \
  -scheme MacOSAdoption \
  -destination 'platform=macOS,arch=arm64' \
  test
```

Expected: app, Unit, and UI targets build and tests pass.

- [ ] **Step 5: Commit**

```bash
git add Tests/AdoptionFixtures/MacOSApp
git commit -m "test(adoption): add macOS Xcode fixture"
```

---

### Task 3: Add the exact VisualDiff fixture manifest and baseline

**Files:**
- Create: `Tests/AdoptionFixtures/MacOSApp/Visual/visual-regression.json`
- Create: `Tests/AdoptionFixtures/MacOSApp/Visual/Baselines/macos-26-arm64-xcode-26.6/main-window.png`
- Create: `scripts/test/test-adoption-fixture-contract.py`

**Interfaces:**
- Profile: `macos-26-arm64-xcode-26.6`
- Capture case: `main-window`
- Current path: `artifacts/visual/current/main-window.png`
- Expected path: `Tests/AdoptionFixtures/MacOSApp/Visual/Baselines/macos-26-arm64-xcode-26.6/main-window.png`

- [ ] **Step 1: Write the failing fixture contract test**

Assert project/scheme/manifest/baseline paths are regular non-symlink files/directories and assert exact manifest fields:

```python
self.assertEqual(manifest["schemaVersion"], 1)
self.assertEqual(manifest["profile"], "macos-26-arm64-xcode-26.6")
self.assertEqual(manifest["cases"], [{
    "id": "main-window",
    "baseline": "git",
    "current": "artifacts/visual/current/main-window.png",
    "expected": "Tests/AdoptionFixtures/MacOSApp/Visual/Baselines/macos-26-arm64-xcode-26.6/main-window.png",
    "maxChangedPixelRatio": 0.0,
    "maxChannelDelta": 0,
}])
```

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/test/test-adoption-fixture-contract.py -v
```

Expected: missing Visual fixture files.

- [ ] **Step 3: Add the exact manifest**

```json
{
  "schemaVersion": 1,
  "profile": "macos-26-arm64-xcode-26.6",
  "cases": [
    {
      "id": "main-window",
      "baseline": "git",
      "current": "artifacts/visual/current/main-window.png",
      "expected": "Tests/AdoptionFixtures/MacOSApp/Visual/Baselines/macos-26-arm64-xcode-26.6/main-window.png",
      "maxChangedPixelRatio": 0.0,
      "maxChannelDelta": 0
    }
  ]
}
```

- [ ] **Step 4: Generate and commit the controlled baseline**

Run the E2E fixture once on `macos-26` with Xcode 26.6 and the same locale/timezone/animation policy used by production E2E. Copy the produced `main-window.png` byte-for-byte into the expected path above. Do not hand-edit or recompress it.

- [ ] **Step 5: Validate with existing VisualDiff tooling**

Run the fixture contract plus the existing manifest validator/VisualDiff suite. Expected: PASS with zero changed pixels when comparing the controlled capture to its baseline under the same profile.

- [ ] **Step 6: Commit**

```bash
git add Tests/AdoptionFixtures/MacOSApp/Visual scripts/test/test-adoption-fixture-contract.py
git commit -m "test(adoption): add visual fixture baseline"
```

---

### Task 4: Add a production-profile-to-runtime output bridge

**Files:**
- Create: `scripts/test/emit-profile-adoption-outputs.py`
- Create: `scripts/test/test-emit-profile-adoption-outputs.py`

**Interfaces:**
- CLI: `emit-profile-adoption-outputs.py --resolved PATH --classified PATH --github-output PATH`.
- Outputs: `adapter`, `coverage_enabled`, `coverage_required`, `e2e_enabled`, `e2e_required`, `visual_enabled`, `visual_required`, `visual_bootstrap`.

- [ ] **Step 1: Write RED tests**

Cover valid SwiftPM/Xcode payloads, missing keys, configurationError=true, non-boolean values, and disagreement between resolved/classified adapter.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/test/test-emit-profile-adoption-outputs.py -v
```

- [ ] **Step 3: Implement strict scalar output emission**

Only accept exact production resolver/classifier keys. Refuse to emit outputs when classifier reports configuration error. Serialize booleans as lowercase `true`/`false`.

- [ ] **Step 4: Run tests and compile validation**

```bash
python3 -m unittest scripts/test/test-emit-profile-adoption-outputs.py -v
python3 -m py_compile scripts/test/emit-profile-adoption-outputs.py scripts/test/test-emit-profile-adoption-outputs.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/test/emit-profile-adoption-outputs.py scripts/test/test-emit-profile-adoption-outputs.py
git commit -m "test(adoption): expose resolved profile outputs"
```

---

### Task 5: Add the GitHub-hosted adoption workflow

**Files:**
- Create: `.github/workflows/test-profile-adoption.yml`
- Create: `scripts/test/test-profile-adoption-wiring.py`
- Modify: `.github/workflows/test-infrastructure.yml`
- Modify: `.github/actionlint.yaml` only when needed for the current pinned actionlint `$/` self-call compatibility gap.

**Interfaces:**
- Exercises `minimal`, `standard`, `macos-app`, and `macos-ui-strict`.
- Uses production resolver/classifier before calling production reusable workflows.

- [ ] **Step 1: Write wiring/security contract tests first**

Assert:

```python
self.assertIn("workflow_dispatch:", workflow)
self.assertNotIn("pull_request_target", workflow)
self.assertNotIn("secrets: inherit", workflow)
self.assertIn("contents: read", workflow)
self.assertIn("reusable-swift-tests.yml", workflow)
self.assertIn("reusable-macos-e2e.yml", workflow)
self.assertIn("reusable-visual-regression.yml", workflow)
for profile in ("minimal", "standard", "macos-app", "macos-ui-strict"):
    self.assertIn(profile, workflow)
```

Also assert no `contents: write`, `pull-requests: write`, release Environment, or Apple secret names occur.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/test/test-profile-adoption-wiring.py -v
```

- [ ] **Step 3: Add prepare jobs that use production policy code**

For each tested profile, write an input JSON with `null` overrides, run production resolver and classifier, then run the output bridge. Use adapter `swiftpm` for `minimal`/`standard` and `xcode` for `macos-app`/`macos-ui-strict`.

- [ ] **Step 4: Execute SwiftPM profiles**

Call `reusable-swift-tests.yml` with `working_directory=Tests/AdoptionFixtures/SwiftPM`.

`minimal` requires `test_result=success` with coverage disabled.

`standard` sets coverage enabled/required from the resolved outputs and sets `bootstrap_coverage: true`; require `test_result=success` and `coverage_result=success`.

- [ ] **Step 5: Execute Xcode Unit/Coverage and E2E profiles**

Use these exact caller values:

```text
working_directory=Tests/AdoptionFixtures/MacOSApp
project_path=MacOSAdoption.xcodeproj
workspace_path=
scheme=MacOSAdoption
destination=platform=macOS,arch=arm64
profile_id=macos-26-arm64-xcode-26.6
```

For both Xcode profiles, Unit/Coverage uses explicit coverage bootstrap and requires raw success. E2E requires raw success and must upload the same-run visual capture artifact.

- [ ] **Step 6: Execute Visual for `macos-ui-strict`**

Call `reusable-visual-regression.yml` with the exact same-run E2E current artifact, fixture manifest path, and required=true. Because the fixture manifest uses `baseline=git`, no rolling-main baseline publication/bootstrap is needed. Require raw Visual result success.

- [ ] **Step 7: Add one final fail-closed verifier**

Use an Ubuntu job with `if: always()` and `needs` on every profile runtime job. It exits nonzero for failure, cancelled, skipped, missing, or unknown required results. Optional behavior is not the purpose of this suite; #16 already covers that runtime contract.

- [ ] **Step 8: Add Test Infrastructure coverage**

Run the output bridge, fixture, and adoption wiring unit tests. Ensure relevant profile/workflow/fixture changes trigger Test Infrastructure.

- [ ] **Step 9: Run local and exact-head runtime verification**

```bash
python3 -m unittest \
  scripts/test/test-adoption-fixture-contract.py \
  scripts/test/test-emit-profile-adoption-outputs.py \
  scripts/test/test-profile-adoption-wiring.py -v
```

Then push a Draft PR and require successful Quality, Tests, Test Infrastructure, and Test Profile Adoption runs on the exact head. Inspect macOS job steps to prove Unit, Coverage export/bootstrap, E2E, artifact upload, and Visual comparison executed rather than skipped.

- [ ] **Step 10: Commit workflow integration**

```bash
git add .github/workflows/test-profile-adoption.yml .github/workflows/test-infrastructure.yml .github/actionlint.yaml scripts/test/test-profile-adoption-wiring.py
git commit -m "test(ci): verify profile adoption runtime"
```

---

### Task 6: Document adoption evidence and finish the PR

**Files:**
- Modify: `docs/TEST_PROFILES.md`
- Modify: `docs/SETUP.md`

- [ ] **Step 1: Document runtime coverage**

State exactly: SwiftPM validates `minimal` and `standard`; the committed Xcode fixture validates `macos-app` and `macos-ui-strict`. Explain that Coverage bootstrap and committed Git visual baseline are fixture mechanics and do not weaken adopter trusted-main baseline rules.

- [ ] **Step 2: Run exact-head verification and review checks**

Require successful Quality, Tests, Test Infrastructure, and Test Profile Adoption workflows and zero unresolved review threads.

- [ ] **Step 3: Commit docs**

```bash
git add docs/TEST_PROFILES.md docs/SETUP.md
git commit -m "docs: record profile adoption verification"
```
