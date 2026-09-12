# Test, E2E, and Visual Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable, secret-free macOS test foundation with unit/integration CI, XCUITest E2E, coverage ratcheting, and hybrid Git + trusted-main visual regression.

**Architecture:** Keep capture adapters separate from comparison. Application tests produce deterministic PNGs and `.xcresult` data; repository-owned tooling validates manifests, compares PNGs, normalizes coverage, and emits machine-readable reports. Rolling baselines are resolved only from successful `main` runs of the expected workflow, while stable baselines stay in Git.

**Tech Stack:** Swift 6 / Swift Package Manager, CoreGraphics, ImageIO, Foundation, XCTest/Swift Testing-compatible `xcodebuild`, XCUITest, `xccov`, SwiftPM coverage JSON, Bash, Python 3 stdlib for lightweight JSON normalization, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-13-test-e2e-visual-regression-design.md`

## Global Constraints

- PR test jobs are secret-free by default and never receive Apple release credentials.
- Standard PR E2E runs on GitHub-hosted macOS without privileged TCC assumptions.
- Privileged system E2E is isolated and never runs arbitrary fork PR code.
- Visual comparison is adapter-agnostic and consumes PNG files under `artifacts/visual/current/`.
- Canonical visual runner is `macos-26`.
- Canonical Xcode path is `/Applications/Xcode_26.6.app/Contents/Developer` for the initial profile.
- Canonical profile changes are reviewable baseline migrations, not silent CI upgrades.
- Git baselines live under `Tests/VisualBaselines/<profile>/` and are never auto-written by CI.
- Rolling baselines come only from successful `main` runs of the expected visual workflow.
- PR visual report retention is 14 days; failed E2E diagnostics retention is 14 days; rolling baseline retention targets 90 days.
- No automatic retries convert a failing required test into a passing required gate.
- Third-party snapshot libraries are optional capture adapters, never comparison authorities.
- Visual manifest paths must be relative and confined to their allowed roots; absolute paths and `..` traversal are rejected.
- Existing `quality.yml`, actionlint, zizmor, ShellCheck, shfmt, Gitleaks, and release trust boundaries must remain green.

---

## File Structure

```text
.github/workflows/
  tests.yml                         # repository-level unit/integration caller
  visual-regression.yml             # repository-level visual caller + main baseline publication
  reusable-swift-tests.yml          # Xcode / SwiftPM unit+integration engine
  reusable-macos-e2e.yml            # standard XCUITest engine and diagnostics
  reusable-visual-regression.yml    # manifest validation, baseline resolution, compare/report
  test-infrastructure.yml           # self-tests for this template's generic tooling

Tools/VisualDiff/
  Package.swift
  Sources/VisualDiffCore/
    ComparisonPolicy.swift
    ComparisonReport.swift
    PixelImage.swift
    VisualComparator.swift
    VisualManifest.swift
    ManifestRunner.swift
  Sources/visual-diff/
    main.swift
  Tests/VisualDiffCoreTests/
    PixelImageTests.swift
    VisualComparatorTests.swift
    VisualManifestTests.swift
    ManifestRunnerTests.swift
    TestImageFactory.swift

scripts/test/
  export-coverage.sh                # Xcode/SwiftPM coverage -> normalized JSON
  compare-coverage.py               # baseline ratchet comparison
  test-compare-coverage.py          # stdlib unittest fixtures

scripts/visual/
  collect-metadata.sh               # canonical execution profile metadata
  resolve-main-baseline.sh          # trusted-main workflow/artifact lookup and download

Tests/VisualRegression/
  visual-regression.example.json

Tests/VisualBaselines/
  .gitkeep

docs/
  TESTING.md
  VISUAL_REGRESSION.md

README.md
CONTRIBUTING.md
.github/pull_request_template.md
.github/CODEOWNERS
```

---

### Task 1: Build the deterministic PNG comparison core

**Files:**
- Create: `Tools/VisualDiff/Package.swift`
- Create: `Tools/VisualDiff/Sources/VisualDiffCore/ComparisonPolicy.swift`
- Create: `Tools/VisualDiff/Sources/VisualDiffCore/ComparisonReport.swift`
- Create: `Tools/VisualDiff/Sources/VisualDiffCore/PixelImage.swift`
- Create: `Tools/VisualDiff/Sources/VisualDiffCore/VisualComparator.swift`
- Create: `Tools/VisualDiff/Tests/VisualDiffCoreTests/TestImageFactory.swift`
- Create: `Tools/VisualDiff/Tests/VisualDiffCoreTests/PixelImageTests.swift`
- Create: `Tools/VisualDiff/Tests/VisualDiffCoreTests/VisualComparatorTests.swift`

**Interfaces:**
- Produces: `ComparisonPolicy(maxChangedPixelRatio:maxChannelDelta:)`
- Produces: `ComparisonReport` with dimensions, changed pixel count/ratio, max channel delta, and pass/fail.
- Produces: `PixelImage.loadPNG(from:)`, `PixelImage.writePNG(to:)`, `PixelImage(width:height:rgba:)`.
- Produces: `VisualComparator.compare(expected:actual:policy:context:) -> ComparisonReport`.

- [ ] **Step 1: Create the Swift package manifest**

```swift
// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VisualDiff",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "VisualDiffCore", targets: ["VisualDiffCore"]),
        .executable(name: "visual-diff", targets: ["visual-diff"]),
    ],
    targets: [
        .target(name: "VisualDiffCore"),
        .executableTarget(name: "visual-diff", dependencies: ["VisualDiffCore"]),
        .testTarget(name: "VisualDiffCoreTests", dependencies: ["VisualDiffCore"]),
    ]
)
```

- [ ] **Step 2: Write failing image round-trip and comparator tests**

```swift
func testIdenticalImagesPassStrictComparison() throws {
    let expected = try TestImageFactory.image(width: 2, height: 2, rgba: [255, 0, 0, 255])
    let actual = expected
    let report = try VisualComparator.compare(
        expected: expected,
        actual: actual,
        policy: .init(maxChangedPixelRatio: 0, maxChannelDelta: 0),
        context: .fixture
    )
    XCTAssertTrue(report.passed)
    XCTAssertEqual(report.changedPixelCount, 0)
    XCTAssertEqual(report.maxChannelDelta, 0)
}

func testSinglePixelChangeFailsStrictComparison() throws {
    let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [0, 0, 0, 255])
    var bytes = expected.rgba
    bytes[0] = 1
    let actual = try PixelImage(width: 2, height: 2, rgba: bytes)
    let report = try VisualComparator.compare(
        expected: expected,
        actual: actual,
        policy: .init(maxChangedPixelRatio: 0, maxChannelDelta: 0),
        context: .fixture
    )
    XCTAssertFalse(report.passed)
    XCTAssertEqual(report.changedPixelCount, 1)
    XCTAssertEqual(report.changedPixelRatio, 0.25, accuracy: 0.000_001)
    XCTAssertEqual(report.maxChannelDelta, 1)
}

func testDimensionMismatchThrows() throws {
    let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [0, 0, 0, 255])
    let actual = try TestImageFactory.solid(width: 3, height: 2, rgba: [0, 0, 0, 255])
    XCTAssertThrowsError(
        try VisualComparator.compare(
            expected: expected,
            actual: actual,
            policy: .init(maxChangedPixelRatio: 0, maxChannelDelta: 0),
            context: .fixture
        )
    )
}
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
swift test --package-path Tools/VisualDiff
```

Expected: compile/test failure because `PixelImage`, `VisualComparator`, and report types do not exist.

- [ ] **Step 4: Implement deterministic PNG normalization and comparison**

Use `CGImageSourceCreateWithURL` to decode. Normalize every image into 8-bit premultiplied RGBA in sRGB using `CGContext`. Define a changed pixel as any RGBA channel whose absolute delta is non-zero; pass only when both `changedPixelRatio <= maxChangedPixelRatio` and the global `maxChannelDelta <= policy.maxChannelDelta`.

Core comparison loop:

```swift
for pixel in 0..<(expected.width * expected.height) {
    let offset = pixel * 4
    let deltas = (0..<4).map {
        abs(Int(expected.rgba[offset + $0]) - Int(actual.rgba[offset + $0]))
    }
    let pixelMax = deltas.max() ?? 0
    if pixelMax > 0 { changedPixelCount += 1 }
    maxChannelDelta = max(maxChannelDelta, pixelMax)
}

let ratio = Double(changedPixelCount) / Double(expected.width * expected.height)
let passed = ratio <= policy.maxChangedPixelRatio && maxChannelDelta <= policy.maxChannelDelta
```

- [ ] **Step 5: Generate a deterministic diff image**

Changed pixels are written as opaque red; unchanged pixels are written as a dimmed copy of expected. This makes large changed regions obvious while preserving layout context.

- [ ] **Step 6: Run the package test suite and verify GREEN**

```bash
swift test --package-path Tools/VisualDiff
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add Tools/VisualDiff
git commit -m "feat: add deterministic visual diff core"
```

---

### Task 2: Add manifest parsing, path confinement, report layout, and CLI

**Files:**
- Create: `Tools/VisualDiff/Sources/VisualDiffCore/VisualManifest.swift`
- Create: `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`
- Create: `Tools/VisualDiff/Sources/visual-diff/main.swift`
- Create: `Tools/VisualDiff/Tests/VisualDiffCoreTests/VisualManifestTests.swift`
- Create: `Tools/VisualDiff/Tests/VisualDiffCoreTests/ManifestRunnerTests.swift`
- Create: `Tests/VisualRegression/visual-regression.example.json`
- Create: `Tests/VisualBaselines/.gitkeep`

**Interfaces:**
- Produces: `VisualManifest.load(from:) -> VisualManifest`.
- Produces: `ManifestCase.Baseline.git` and `.rollingMain`.
- Produces CLI:
  - `visual-diff validate-manifest --manifest <path> --repo-root <path>`
  - `visual-diff compare-manifest --manifest <path> --repo-root <path> --rolling-root <path> --output <path> --current-sha <sha> --baseline-run-id <id-or-empty>`

- [ ] **Step 1: Write failing manifest validation tests**

```swift
func testRejectsAbsoluteCurrentPath() throws {
    let json = #"{"schemaVersion":1,"profile":"p","cases":[{"id":"x","baseline":"git","current":"/tmp/x.png","expected":"Tests/VisualBaselines/p/x.png","maxChangedPixelRatio":0,"maxChannelDelta":0}]}"#
    XCTAssertThrowsError(try VisualManifest.decode(Data(json.utf8)))
}

func testRejectsParentTraversal() throws {
    let json = #"{"schemaVersion":1,"profile":"p","cases":[{"id":"x","baseline":"git","current":"artifacts/visual/current/../secret.png","expected":"Tests/VisualBaselines/p/x.png","maxChangedPixelRatio":0,"maxChannelDelta":0}]}"#
    XCTAssertThrowsError(try VisualManifest.decode(Data(json.utf8)))
}
```

- [ ] **Step 2: Write failing runner tests for Git and rolling cases**

Create temporary repo/current/baseline directories. Assert Git cases read only from `Tests/VisualBaselines`, rolling cases read only from the supplied rolling root, and output is always:

```text
visual-report/<case-id>/expected.png
visual-report/<case-id>/actual.png
visual-report/<case-id>/diff.png
visual-report/<case-id>/report.json
```

- [ ] **Step 3: Run tests and verify RED**

```bash
swift test --package-path Tools/VisualDiff
```

- [ ] **Step 4: Implement manifest types and root confinement**

Reject:

```text
absolute paths
empty case ids
duplicate case ids
schemaVersion != 1
negative tolerances
maxChangedPixelRatio > 1
maxChannelDelta > 255
`..` path components
Git cases without expected path
Git expected paths outside Tests/VisualBaselines
current paths outside artifacts/visual/current
```

Use standardized URL prefix checks after syntactic validation as a second defense.

- [ ] **Step 5: Implement report JSON and CLI exit semantics**

`compare-manifest` exits `0` only when every comparable case passes. Missing Git baseline, capture missing, profile mismatch passed into the runner, or threshold failure exits non-zero. Bootstrap rolling cases are represented separately by the workflow and are not treated as a false match.

- [ ] **Step 6: Add the example manifest**

```json
{
  "schemaVersion": 1,
  "profile": "macos-26-arm64-xcode-26.6",
  "cases": [
    {
      "id": "settings-light",
      "baseline": "git",
      "current": "artifacts/visual/current/settings-light.png",
      "expected": "Tests/VisualBaselines/macos-26-arm64-xcode-26.6/settings-light.png",
      "maxChangedPixelRatio": 0.0,
      "maxChannelDelta": 0
    },
    {
      "id": "large-dynamic-screen",
      "baseline": "rolling-main",
      "current": "artifacts/visual/current/large-dynamic-screen.png",
      "maxChangedPixelRatio": 0.001,
      "maxChannelDelta": 8
    }
  ]
}
```

- [ ] **Step 7: Run tests and CLI smoke checks**

```bash
swift test --package-path Tools/VisualDiff
swift run --package-path Tools/VisualDiff visual-diff validate-manifest \
  --manifest Tests/VisualRegression/visual-regression.example.json \
  --repo-root "$PWD"
```

- [ ] **Step 8: Commit**

```bash
git add Tools/VisualDiff Tests/VisualRegression Tests/VisualBaselines
git commit -m "feat: add visual manifest runner and CLI"
```

---

### Task 3: Add coverage normalization and ratchet tests

**Files:**
- Create: `scripts/test/export-coverage.sh`
- Create: `scripts/test/compare-coverage.py`
- Create: `scripts/test/test-compare-coverage.py`

**Interfaces:**
- `export-coverage.sh xcode <xcresult> <output.json>`
- `export-coverage.sh swiftpm <swiftpm-codecov.json> <output.json>`
- `compare-coverage.py --current <json> --baseline <json> --max-regression <ratio>`
- Normalized JSON:

```json
{
  "schemaVersion": 1,
  "overallLineCoverage": 0.812345,
  "targets": {
    "AppCore": 0.91,
    "AppUI": 0.73
  }
}
```

- [ ] **Step 1: Write RED tests for coverage comparison**

`test-compare-coverage.py` must assert:

```python
self.assertEqual(run_compare(current=0.80, baseline=0.80, tolerance=0.001), 0)
self.assertEqual(run_compare(current=0.7995, baseline=0.80, tolerance=0.001), 0)
self.assertNotEqual(run_compare(current=0.79, baseline=0.80, tolerance=0.001), 0)
```

Also test malformed JSON, missing baseline, and target-level regression output.

- [ ] **Step 2: Run and verify RED**

```bash
python3 -m unittest scripts/test/test-compare-coverage.py -v
```

- [ ] **Step 3: Implement the comparator**

Use `decimal.Decimal` rather than binary float comparisons. Exit `0` when `baseline - current <= maxRegression`; otherwise print each regressed metric and exit `1`.

- [ ] **Step 4: Implement Xcode coverage export**

```bash
xcrun xccov view --report --json "$xcresult" >"$raw_json"
```

Parse project/target line coverage into the normalized schema with Python stdlib.

- [ ] **Step 5: Implement SwiftPM coverage export**

The caller runs:

```bash
swift test --enable-code-coverage
swift test --show-codecov-path
```

The second command returns SwiftPM's exported coverage JSON path. Parse the LLVM export JSON into the same normalized schema.

- [ ] **Step 6: Verify scripts**

```bash
python3 -m unittest scripts/test/test-compare-coverage.py -v
bash -n scripts/test/export-coverage.sh
shellcheck scripts/test/export-coverage.sh
shfmt -d -i 2 -ci scripts/test/export-coverage.sh
```

- [ ] **Step 7: Commit**

```bash
git add scripts/test
git commit -m "feat: add coverage baseline ratchet tooling"
```

---

### Task 4: Add reusable Swift unit/integration workflow

**Files:**
- Create: `.github/workflows/reusable-swift-tests.yml`
- Create: `.github/workflows/tests.yml`

**Interfaces:**
- Inputs:
  - `adapter`: `xcode` or `swiftpm`
  - `project_path`: optional
  - `workspace_path`: optional
  - `scheme`: required for xcode
  - `test_plan`: optional
  - `destination`: default `platform=macOS,arch=arm64`
  - `enable_coverage`: boolean
  - `coverage_baseline_artifact`: default `coverage-baseline`
  - `coverage_max_regression`: default `0.001`
  - `bootstrap_coverage`: boolean
- Permissions: `contents: read`; `actions: read` only when resolving main baseline.

- [ ] **Step 1: Add a workflow contract validation fixture to `test-infrastructure.yml` later used by actionlint**

Before implementation, document exact job names:

```text
Tests / Unit and integration
Tests / Coverage regression
```

These names must remain stable for Rulesets.

- [ ] **Step 2: Implement the Xcode adapter without arbitrary shell input**

Construct arguments from validated inputs:

```bash
xcodebuild test \
  -workspace "$WORKSPACE_PATH" \
  -scheme "$SCHEME" \
  -destination "$DESTINATION" \
  -resultBundlePath "$RUNNER_TEMP/unit-tests.xcresult" \
  -enableCodeCoverage YES
```

Use `-project` instead when `project_path` is supplied. Exactly one of workspace/project is required for `adapter=xcode`.

- [ ] **Step 3: Implement the SwiftPM adapter**

```bash
swift test --enable-code-coverage
CODECOV_PATH="$(swift test --show-codecov-path)"
scripts/test/export-coverage.sh swiftpm "$CODECOV_PATH" artifacts/test/coverage-summary.json
```

When coverage is disabled, run plain `swift test`.

- [ ] **Step 4: Upload test diagnostics and normalized coverage**

Test result/coverage artifacts use 14-day retention for PR diagnostics. Coverage baseline publication is not performed by PR runs.

- [ ] **Step 5: Resolve trusted main coverage baseline**

Use the same trust constraints later shared with visual baseline resolution: current repository, branch `main`, expected workflow, successful run, expected artifact name. In bootstrap mode, missing baseline is reported as bootstrap instead of success-by-comparison.

- [ ] **Step 6: Validate workflow syntax/security**

```bash
actionlint .github/workflows/reusable-swift-tests.yml .github/workflows/tests.yml
zizmor .github/workflows/reusable-swift-tests.yml .github/workflows/tests.yml
```

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/reusable-swift-tests.yml .github/workflows/tests.yml
git commit -m "feat: add reusable unit and integration test workflow"
```

---

### Task 5: Add Standard macOS XCUITest E2E workflow

**Files:**
- Create: `.github/workflows/reusable-macos-e2e.yml`
- Create: `scripts/visual/collect-metadata.sh`

**Interfaces:**
- Inputs:
  - `workspace_path` / `project_path`
  - `scheme`
  - `test_plan` or UI-test target configuration
  - `destination`: default `platform=macOS,arch=arm64`
  - `runner`: default and documented canonical `macos-26`
  - `xcode_path`: default `/Applications/Xcode_26.6.app/Contents/Developer`
  - `visual_output_dir`: default `artifacts/visual/current`
- Outputs/artifacts:
  - `e2e.xcresult`
  - exported screenshot attachments
  - canonical `profile.json`

- [ ] **Step 1: Add a metadata script testable without Xcode execution**

The script writes:

```json
{
  "schemaVersion": 1,
  "profile": "macos-26-arm64-xcode-26.6",
  "runnerOS": "macOS",
  "runnerArch": "ARM64",
  "xcodePath": "/Applications/Xcode_26.6.app/Contents/Developer",
  "xcodeVersion": "Xcode 26.6",
  "locale": "en_US.UTF-8",
  "timezone": "UTC"
}
```

Values are collected from environment and `xcodebuild -version`, not hard-coded except the expected profile input.

- [ ] **Step 2: Implement `build-for-testing`**

```bash
xcodebuild build-for-testing \
  -workspace "$WORKSPACE_PATH" \
  -scheme "$SCHEME" \
  -destination "$DESTINATION" \
  -derivedDataPath "$RUNNER_TEMP/DerivedData"
```

- [ ] **Step 3: Implement `test-without-building` with `.xcresult`**

```bash
xcodebuild test-without-building \
  -workspace "$WORKSPACE_PATH" \
  -scheme "$SCHEME" \
  -destination "$DESTINATION" \
  -derivedDataPath "$RUNNER_TEMP/DerivedData" \
  -resultBundlePath "$RUNNER_TEMP/e2e.xcresult"
```

Append `-testPlan "$TEST_PLAN"` when configured.

- [ ] **Step 4: Export attachments into the PNG contract directory**

Use current `xcresulttool` attachment export support when available. If export is unsupported for a runner/toolchain, preserve `.xcresult` and fail with a diagnostic rather than pretending visual capture succeeded.

- [ ] **Step 5: Upload diagnostics with `if: always()` and 14-day retention**

The blocking test result remains failed even though artifacts upload successfully.

- [ ] **Step 6: Enforce secret-free permissions**

```yaml
permissions:
  contents: read
```

No Environment, Apple secrets, production credentials, or `pull_request_target`.

- [ ] **Step 7: Validate actionlint/zizmor/ShellCheck/shfmt and commit**

```bash
actionlint .github/workflows/reusable-macos-e2e.yml
zizmor .github/workflows/reusable-macos-e2e.yml
shellcheck scripts/visual/collect-metadata.sh
shfmt -d -i 2 -ci scripts/visual/collect-metadata.sh
git add .github/workflows/reusable-macos-e2e.yml scripts/visual/collect-metadata.sh
git commit -m "feat: add standard macOS E2E workflow"
```

---

### Task 6: Add Git-baseline visual regression workflow

**Files:**
- Create: `.github/workflows/reusable-visual-regression.yml`
- Create: `.github/workflows/visual-regression.yml`

**Interfaces:**
- Inputs:
  - `manifest_path`
  - `profile`
  - `current_artifact_name`
  - `bootstrap_rolling`
  - `rolling_artifact_name`
  - `runner`: default `macos-26`
  - `xcode_path`: default `/Applications/Xcode_26.6.app/Contents/Developer`
- Stable check: `Visual Regression / Compare UI`.

- [ ] **Step 1: Validate the manifest before downloading any baseline**

```bash
swift run --package-path Tools/VisualDiff visual-diff validate-manifest \
  --manifest "$MANIFEST_PATH" \
  --repo-root "$GITHUB_WORKSPACE"
```

- [ ] **Step 2: Download current capture artifact produced by E2E/capture job**

Extract only into `artifacts/visual/current`. Reject unexpected archive paths after extraction by checking the resulting tree.

- [ ] **Step 3: Compare Git-baseline cases**

Run `compare-manifest` with an empty rolling root only when the manifest contains no rolling cases. Missing Git expected PNG must fail explicitly.

- [ ] **Step 4: Always upload visual-report artifact**

Artifact layout:

```text
visual-report/<case-id>/expected.png
visual-report/<case-id>/actual.png
visual-report/<case-id>/diff.png
visual-report/<case-id>/report.json
```

Retention: `14` days.

- [ ] **Step 5: Write `$GITHUB_STEP_SUMMARY` without PR write permissions**

Summary table columns:

```text
Case | Baseline | Changed pixels | Ratio | Max delta | Result
```

- [ ] **Step 6: Validate and commit**

```bash
actionlint .github/workflows/reusable-visual-regression.yml .github/workflows/visual-regression.yml
zizmor .github/workflows/reusable-visual-regression.yml .github/workflows/visual-regression.yml
git add .github/workflows/reusable-visual-regression.yml .github/workflows/visual-regression.yml
git commit -m "feat: add Git-baseline visual regression workflow"
```

---

### Task 7: Add trusted rolling-main baseline resolution and publication

**Files:**
- Create: `scripts/visual/resolve-main-baseline.sh`
- Modify: `.github/workflows/reusable-visual-regression.yml`
- Modify: `.github/workflows/visual-regression.yml`

**Interfaces:**
- Resolver arguments:

```text
--repository owner/repo
--workflow visual-regression.yml
--artifact visual-baseline-macos-26-arm64-xcode-26.6
--output <directory>
--token-env GITHUB_TOKEN
```

- [ ] **Step 1: Write shell-level negative tests using a stubbed `gh` executable**

Fixtures must verify rejection of:

```text
PR runs
non-main branch runs
failed runs
wrong workflow ids/names
wrong artifact names
expired/missing artifacts
```

- [ ] **Step 2: Run tests and verify RED**

Use a temporary PATH containing the stubbed `gh` fixture. Expected: resolver test fails before implementation.

- [ ] **Step 3: Implement bounded trusted lookup**

Use `gh api` only with repository-derived fixed endpoint shapes. Select the newest run where all are true:

```text
head_branch == main
event == push
conclusion == success
workflow == visual-regression.yml
```

Then select the exact expected artifact name. Never fall back to a PR run or differently named artifact.

- [ ] **Step 4: Verify rolling `profile.json` matches the current profile before compare**

Mismatch exits before pixel comparison and prints both expected/current metadata.

- [ ] **Step 5: Implement bootstrap semantics**

When no rolling baseline exists:

```text
bootstrap_rolling=true  -> report non-comparable bootstrap state; do not claim match
bootstrap_rolling=false -> fail
```

- [ ] **Step 6: Publish rolling baseline only on trusted successful `main`**

Publication condition must include:

```yaml
if: >-
  github.event_name == 'push' &&
  github.ref == 'refs/heads/main' &&
  success()
```

Upload the current rolling cases plus `profile.json` with 90-day retention.

- [ ] **Step 7: Run shell/workflow validators and commit**

```bash
shellcheck scripts/visual/resolve-main-baseline.sh
shfmt -d -i 2 -ci scripts/visual/resolve-main-baseline.sh
actionlint .github/workflows/reusable-visual-regression.yml .github/workflows/visual-regression.yml
zizmor .github/workflows/reusable-visual-regression.yml .github/workflows/visual-regression.yml
git add scripts/visual/resolve-main-baseline.sh .github/workflows/reusable-visual-regression.yml .github/workflows/visual-regression.yml
git commit -m "feat: add trusted rolling visual baselines"
```

---

### Task 8: Add template self-tests and repository hygiene integration

**Files:**
- Create: `.github/workflows/test-infrastructure.yml`
- Modify: `.github/workflows/quality.yml`

**Interfaces:**
- Stable check: `Test Infrastructure / Generic tooling`.
- Trigger paths include `Tools/VisualDiff/**`, `scripts/test/**`, `scripts/visual/**`, and the new workflow files.

- [ ] **Step 1: Make the self-test workflow run deterministic tool tests**

```bash
swift test --package-path Tools/VisualDiff
python3 -m unittest scripts/test/test-compare-coverage.py -v
```

- [ ] **Step 2: Add shell lint coverage for new scripts to existing hygiene job**

Existing recursive `scripts/**/*.sh` checks should already catch them; add an assertion/smoke step only if the current workflow does not recurse.

- [ ] **Step 3: Add a manifest CLI smoke test**

```bash
swift run --package-path Tools/VisualDiff visual-diff validate-manifest \
  --manifest Tests/VisualRegression/visual-regression.example.json \
  --repo-root "$PWD"
```

- [ ] **Step 4: Run actionlint/zizmor and commit**

```bash
actionlint
zizmor .github/workflows

git add .github/workflows/test-infrastructure.yml .github/workflows/quality.yml
git commit -m "ci: add generic test infrastructure validation"
```

---

### Task 9: Document testing, visual review, baseline updates, and privileged E2E

**Files:**
- Create: `docs/TESTING.md`
- Create: `docs/VISUAL_REGRESSION.md`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `.github/pull_request_template.md`
- Modify: `.github/CODEOWNERS`

**Interfaces:**
- Documentation must distinguish Standard E2E from Privileged system E2E.
- Git baseline changes require explicit review.
- Rolling baselines advance automatically only after trusted `main` success.

- [ ] **Step 1: Document the app test-mode contract**

Require app adopters to provide stable accessibility identifiers and deterministic launch controls for data dir, fixtures, networking, time/random seed, animations, and Light/Dark appearance where relevant.

- [ ] **Step 2: Document intentional Git-baseline update flow**

```text
1. run/capture the changed UI under the canonical profile
2. copy reviewed PNGs into Tests/VisualBaselines/<profile>/
3. inspect expected/current/diff artifacts
4. commit baseline PNGs in the same PR as the UI change
5. do not raise tolerances merely to hide unexplained changes
```

- [ ] **Step 3: Document rolling-baseline bootstrap and migration**

Include first-run bootstrap, 90-day retention implications, canonical profile changes, and profile mismatch recovery.

- [ ] **Step 4: Document privileged system E2E**

Specify a separate protected test Environment and optional prepared/self-hosted runner. Explicitly forbid reuse of `release` secrets.

- [ ] **Step 5: Update PR checklist**

Add checkboxes for unit/integration, E2E, visual artifacts, intentional baseline changes, and accessibility identifiers.

- [ ] **Step 6: Protect visual baselines in CODEOWNERS**

Add:

```text
/Tests/VisualBaselines/ @Lamy210
/.github/workflows/*test*.yml @Lamy210
/.github/workflows/*visual*.yml @Lamy210
/Tools/VisualDiff/ @Lamy210
```

- [ ] **Step 7: Commit**

```bash
git add docs README.md CONTRIBUTING.md .github/pull_request_template.md .github/CODEOWNERS
git commit -m "docs: document test and visual regression workflow"
```

---

### Task 10: Final verification, PR review, and template merge

**Files:**
- Verify all files in this plan.
- Update PR #2 summary/status only after verification.

- [ ] **Step 1: Run all deterministic local/tooling checks**

```bash
swift test --package-path Tools/VisualDiff
python3 -m unittest scripts/test/test-compare-coverage.py -v
find scripts -type f -name '*.sh' -print0 | xargs -0 shellcheck
shfmt -d -i 2 -ci scripts
actionlint
zizmor .github/workflows
```

Expected: all pass.

- [ ] **Step 2: Verify no secrets or unexpected broad permissions were introduced**

Inspect every new workflow. Ordinary test/visual jobs must not contain:

```text
pull_request_target
secrets: inherit
environment: release
contents: write
pull-requests: write
```

unless a separately justified trusted-main publication job requires only the narrow permission documented in the spec.

- [ ] **Step 3: Verify changed-file scope against the plan**

```bash
git diff --name-only main...HEAD
```

Expected: only planned workflow/tool/script/test/doc paths.

- [ ] **Step 4: Confirm latest PR-head CI**

Required before merge:

```text
Quality / Repository hygiene = success
Quality / GitHub Actions security = success
Quality / Secret scan = success
Swift Quality = success
Test Infrastructure / Generic tooling = success
```

- [ ] **Step 5: Resolve all review threads and squash-merge PR #2**

Use expected-head-SHA protection on the merge.

- [ ] **Step 6: Verify post-merge `main` CI**

Confirm the same generic checks succeed on the merge commit before treating the template phase as complete.

---

### Task 11: Adopter validation in one real macOS application

**Files:**
- Separate application repository, recommended first target: `Lamy210/SchneeBar` or `Lamy210/SchneeGlass`.
- This is a follow-up PR in the adopter repository, not part of the template PR.

**Interfaces:**
- Consume the template contracts without granting release secrets to PR tests.
- Produce at least one XCUITest screenshot into `artifacts/visual/current/`.

- [ ] **Step 1: Inspect the adopter's Xcode project, test targets, accessibility identifiers, and current CI**

Do not assume scheme/test-plan names; derive them from the repository.

- [ ] **Step 2: Add one deterministic critical-flow Standard E2E**

Minimum proof:

```text
launch app in test mode
reach one stable screen/popover/window
assert an accessibility identifier
capture PNG attachment/output
```

- [ ] **Step 3: Add one Git-baseline case and one rolling-main case**

Both must coexist in the same `visual-regression.json`.

- [ ] **Step 4: Demonstrate a failing UI diff**

Make a temporary test-only visual change, verify `expected/actual/diff/report.json` are produced, then revert the temporary change.

- [ ] **Step 5: Demonstrate coverage ratchet behavior**

Verify a material decrease fails and an unchanged/improved result passes.

- [ ] **Step 6: Merge adopter PR only after its own CI is green**

This closes the end-to-end acceptance criteria from the design spec.
