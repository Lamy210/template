# Test, E2E, and Visual Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable, secret-free macOS unit/integration/E2E testing, coverage ratcheting, and hybrid Git + trusted-main visual regression to the template.

**Architecture:** Capture and comparison are separate contracts. Adopter tests write deterministic PNGs to `artifacts/visual/current/`; repository-owned Swift tooling validates manifests and compares images. A single trusted-main artifact resolver supplies both rolling visual baselines and coverage baselines, ensuring neither can originate from PR runs.

**Tech Stack:** Swift 6, Swift Package Manager, Foundation, CoreGraphics, ImageIO, XCTest/XCUITest, `xcodebuild`, `xccov`, SwiftPM coverage JSON, Bash, Python 3 standard library, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-13-test-e2e-visual-regression-design.md`

## Global Constraints

- Ordinary PR tests never receive Developer ID, App Store Connect, production, or release Environment secrets.
- Standard E2E runs on GitHub-hosted macOS and assumes no privileged TCC grants.
- Permission-sensitive E2E is a separate optional protected workflow and never runs arbitrary fork PR code.
- Canonical visual runner: `macos-26`.
- Initial canonical Xcode: `/Applications/Xcode_26.6.app/Contents/Developer`.
- Changing canonical runner/Xcode/profile requires reviewed baseline migration.
- Git visual baselines live under `Tests/VisualBaselines/<profile>/`; CI never commits or updates them.
- Rolling visual and coverage baselines come only from successful `push` runs on `main` of an explicitly named workflow.
- PR visual/E2E diagnostic retention: 14 days. Rolling baseline retention target: 90 days.
- Required tests are not automatically retried to turn flaky failures green.
- Visual manifest paths are relative and confined to allowed roots; absolute paths and `..` are rejected.
- No third-party snapshot package is required by the comparison layer.
- Existing Quality, Swift Quality, actionlint, zizmor, ShellCheck, shfmt, Gitleaks, and release trust boundaries remain green.

## File Structure

```text
.github/workflows/
  tests.yml
  visual-regression.yml
  reusable-swift-tests.yml
  reusable-macos-e2e.yml
  reusable-visual-regression.yml
  test-infrastructure.yml

Tools/VisualDiff/
  Package.swift
  Sources/VisualDiffCore/
    ComparisonPolicy.swift
    ComparisonReport.swift
    PixelImage.swift
    VisualComparator.swift
    VisualManifest.swift
    ProfileMetadata.swift
    ManifestRunner.swift
  Sources/visual-diff/main.swift
  Tests/VisualDiffCoreTests/
    TestImageFactory.swift
    PixelImageTests.swift
    VisualComparatorTests.swift
    VisualManifestTests.swift
    ManifestRunnerTests.swift

scripts/ci/
  resolve-trusted-main-artifact.sh
  test-resolve-trusted-main-artifact.sh
scripts/test/
  export-coverage.sh
  compare-coverage.py
  test-compare-coverage.py
scripts/visual/
  collect-metadata.sh

Tests/VisualRegression/visual-regression.example.json
Tests/VisualBaselines/.gitkeep

docs/TESTING.md
docs/VISUAL_REGRESSION.md
README.md
CONTRIBUTING.md
.github/pull_request_template.md
.github/CODEOWNERS
```

---

### Task 1: Deterministic PNG comparison core

**Files:**
- Create `Tools/VisualDiff/Package.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ComparisonPolicy.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ComparisonReport.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/PixelImage.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/VisualComparator.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/TestImageFactory.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/PixelImageTests.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/VisualComparatorTests.swift`

**Interfaces:**

```swift
public struct ComparisonPolicy: Sendable, Equatable {
    public let maxChangedPixelRatio: Double
    public let maxChannelDelta: UInt8
}

public struct ComparisonResult: Sendable, Equatable {
    public let report: ComparisonReport
    public let diff: PixelImage
}

public enum VisualComparator {
    public static func compare(
        expected: PixelImage,
        actual: PixelImage,
        policy: ComparisonPolicy
    ) -> ComparisonResult
}
```

- [ ] Write RED tests for identical pixels, one changed pixel, tolerated ratio, tolerated channel delta, and dimension mismatch.

```swift
func testIdenticalImagesPassStrictComparison() throws {
    let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [255, 0, 0, 255])
    let result = VisualComparator.compare(
        expected: expected,
        actual: expected,
        policy: .init(maxChangedPixelRatio: 0, maxChannelDelta: 0)
    )
    XCTAssertTrue(result.report.passed)
    XCTAssertEqual(result.report.changedPixelCount, 0)
}

func testSinglePixelChangeFailsStrictComparison() throws {
    let expected = try TestImageFactory.solid(width: 2, height: 2, rgba: [0, 0, 0, 255])
    var bytes = expected.rgba
    bytes[0] = 1
    let actual = try PixelImage(width: 2, height: 2, rgba: bytes)
    let result = VisualComparator.compare(
        expected: expected,
        actual: actual,
        policy: .init(maxChangedPixelRatio: 0, maxChannelDelta: 0)
    )
    XCTAssertFalse(result.report.passed)
    XCTAssertEqual(result.report.changedPixelCount, 1)
    XCTAssertEqual(result.report.changedPixelRatio, 0.25, accuracy: 0.000_001)
    XCTAssertEqual(result.report.maxChannelDelta, 1)
}
```

- [ ] Run `swift test --package-path Tools/VisualDiff`; verify RED because types do not exist.
- [ ] Implement `PixelImage` PNG decode/write using `CGImageSource`, `CGImageDestination`, and an 8-bit sRGB RGBA `CGContext`.
- [ ] Validate `rgba.count == width * height * 4`, width/height > 0.
- [ ] Implement comparison: a pixel is changed when any RGBA channel delta is non-zero; pass only when changed-pixel ratio and global maximum channel delta are both within policy.
- [ ] For equal dimensions, diff image uses dimmed expected pixels for unchanged regions and opaque red for changed pixels.
- [ ] For dimension mismatch, return `passed=false`, `dimensionMismatch=true`, both dimensions in the report, and a deterministic side-by-side PNG with a red separator; do not throw and lose diagnostics.
- [ ] Run `swift test --package-path Tools/VisualDiff`; verify GREEN.
- [ ] Commit: `feat: add deterministic visual diff core`.

---

### Task 2: Manifest, profile metadata, path confinement, and CLI

**Files:**
- Create `Tools/VisualDiff/Sources/VisualDiffCore/VisualManifest.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ProfileMetadata.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`
- Create `Tools/VisualDiff/Sources/visual-diff/main.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/VisualManifestTests.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/ManifestRunnerTests.swift`
- Create `Tests/VisualRegression/visual-regression.example.json`
- Create `Tests/VisualBaselines/.gitkeep`

**Interfaces:**

```text
visual-diff validate-manifest \
  --manifest <json> \
  --repo-root <dir>

visual-diff compare-manifest \
  --manifest <json> \
  --repo-root <dir> \
  --current-profile <profile.json> \
  --rolling-root <dir-or-empty> \
  --rolling-profile <profile.json-or-empty> \
  --output <dir> \
  --current-sha <sha> \
  --baseline-run-id <id-or-empty> \
  --bootstrap-rolling <true|false>
```

- [ ] Write RED tests rejecting absolute paths, `..`, duplicate ids, invalid schema version, ratio outside `0...1`, channel delta outside `0...255`, Git case without `expected`, Git baseline outside `Tests/VisualBaselines`, and current path outside `artifacts/visual/current`.
- [ ] Write RED tests for profile mismatch before comparison.
- [ ] Write RED tests that Git cases resolve only under repo-root Git baselines and rolling cases only under supplied rolling root.
- [ ] Run `swift test --package-path Tools/VisualDiff`; verify RED.
- [ ] Implement manifest decoding and standardized-URL root confinement as a second defense after component validation.
- [ ] Implement `ProfileMetadata` decoding. `manifest.profile` must equal current profile id. If a rolling baseline exists, its profile id must also match before any rolling pixel comparison.
- [ ] Implement per-case report layout:

```text
visual-report/<case-id>/expected.png
visual-report/<case-id>/actual.png
visual-report/<case-id>/diff.png
visual-report/<case-id>/report.json
```

`report.json` includes case id, baseline source/reference, current SHA, profile id, expected/actual dimensions, dimension mismatch, changed count/ratio, maximum delta, status (`passed`, `failed`, `bootstrap`), and threshold values.
- [ ] Implement bootstrap: missing rolling baseline + `bootstrap=true` yields explicit `bootstrap` status, never `passed`; missing baseline + bootstrap false fails.
- [ ] CLI exits non-zero when any comparable case fails or required baseline/capture/profile is missing; bootstrap-only rolling cases do not masquerade as comparisons.
- [ ] Add example manifest with one strict Git case and one tolerant rolling-main case.
- [ ] Run unit tests plus `visual-diff validate-manifest` smoke command; verify GREEN.
- [ ] Commit: `feat: add visual manifest runner and CLI`.

---

### Task 3: Shared trusted-main artifact resolver

**Files:**
- Create `scripts/ci/resolve-trusted-main-artifact.sh`
- Create `scripts/ci/test-resolve-trusted-main-artifact.sh`

**Interface:**

```text
resolve-trusted-main-artifact.sh \
  --repository owner/repo \
  --workflow <workflow-file.yml> \
  --artifact <exact-name> \
  --output <directory>
```

Uses `GH_TOKEN` from environment. No arbitrary URL argument is accepted.

- [ ] Write a RED shell test that injects a stub `gh` on `PATH` and returns fixture JSON.
- [ ] Fixtures cover: successful `main` push accepted; PR run rejected; non-main rejected; failure rejected; exact artifact-name mismatch rejected; expired artifact rejected; no successful main run returns a distinct `not-found` exit code.
- [ ] Run `bash scripts/ci/test-resolve-trusted-main-artifact.sh`; verify RED before resolver exists.
- [ ] Implement fixed endpoint shapes only:

```text
repos/<owner>/<repo>/actions/workflows/<workflow>/runs?branch=main&event=push&status=success&per_page=20
repos/<owner>/<repo>/actions/runs/<run-id>/artifacts?per_page=100
repos/<owner>/<repo>/actions/artifacts/<artifact-id>/zip
```

- [ ] Re-validate returned run fields `head_branch == main`, `event == push`, `conclusion == success` even though query filters are present.
- [ ] Require exact artifact name and `expired == false`.
- [ ] Use at most three bounded API attempts with short backoff for infrastructure failure; never fall back to another branch/run class/artifact.
- [ ] Download ZIP to a temp file, unzip into a fresh output directory, and reject `../` or absolute archive members before extraction.
- [ ] Run resolver tests, ShellCheck, and shfmt; verify GREEN.
- [ ] Commit: `feat: add trusted main artifact resolver`.

---

### Task 4: Coverage normalization and ratchet

**Files:**
- Create `scripts/test/export-coverage.sh`
- Create `scripts/test/compare-coverage.py`
- Create `scripts/test/test-compare-coverage.py`

**Normalized schema:**

```json
{
  "schemaVersion": 1,
  "overallLineCoverage": 0.812345,
  "targets": {
    "AppCore": 0.91
  }
}
```

`targets` may be empty when source tooling does not provide a trustworthy target grouping.

- [ ] Write RED `unittest` cases: equal passes; decrease within `0.001` passes; substantive decrease fails; malformed schema fails; target regression is listed when target values exist.
- [ ] Run `python3 -m unittest scripts/test/test-compare-coverage.py -v`; verify RED.
- [ ] Implement comparison using `decimal.Decimal`; policy is `baseline - current <= maxRegression` for overall and common target keys.
- [ ] Implement Xcode exporter: `xcrun xccov view --report --json <xcresult>` then normalize overall/target `lineCoverage`.
- [ ] Implement SwiftPM exporter from the JSON file returned by `swift test --show-codecov-path`; normalize LLVM export summary, leaving targets empty if no stable grouping is available.
- [ ] Verify unit tests, `bash -n`, ShellCheck, and shfmt.
- [ ] Commit: `feat: add coverage baseline ratchet tooling`.

---

### Task 5: Reusable unit/integration workflow and coverage baseline

**Files:**
- Create `.github/workflows/reusable-swift-tests.yml`
- Create `.github/workflows/tests.yml`

**Reusable inputs:**

```text
adapter: xcode | swiftpm
project_path / workspace_path
scheme
test_plan
destination (default: platform=macOS,arch=arm64)
enable_coverage
coverage_max_regression (default: 0.001)
bootstrap_coverage
coverage_artifact_name
```

**Caller configuration:** `tests.yml` reads repository variables. If `MACOS_TEST_ADAPTER` is empty, it runs a small `not-configured` job and a stable final gate but does not pretend application tests executed. Documentation forbids making the gate required until the repository is configured.

**Stable final check:** `Tests / Test gate`.

- [ ] Implement Xcode adapter input validation: exactly one of project/workspace; non-empty scheme.
- [ ] Xcode command uses `-resultBundlePath`, configured destination, optional `-testPlan`, and `-enableCodeCoverage YES` when enabled.
- [ ] SwiftPM command uses `swift test`; with coverage: `swift test --enable-code-coverage`, then `swift test --show-codecov-path` and Task 4 exporter.
- [ ] On PR, use Task 3 resolver with workflow `tests.yml` and exact configured coverage baseline artifact. `actions: read` is granted only to the job that resolves the baseline.
- [ ] Missing baseline: bootstrap true -> explicit bootstrap summary; bootstrap false -> gate failure.
- [ ] Compare current coverage via Task 4 tool.
- [ ] On successful `main` push only, upload normalized coverage baseline artifact with 90-day retention.
- [ ] Upload `.xcresult`/coverage diagnostics with 14-day retention on failure/PR review.
- [ ] `tests.yml` uses concurrency cancellation per PR ref.
- [ ] Add final `Test gate` job with `if: always()` that fails if configured unit/integration or coverage jobs fail; when unconfigured it states `NOT CONFIGURED` and succeeds only as a template bootstrap state.
- [ ] Run actionlint and zizmor on both files.
- [ ] Commit: `feat: add reusable unit and integration test workflow`.

---

### Task 6: Standard macOS XCUITest E2E and deterministic capture contract

**Files:**
- Create `.github/workflows/reusable-macos-e2e.yml`
- Create `scripts/visual/collect-metadata.sh`

**Capture contract for adopter UI tests:**

```swift
func recordVisual(_ id: String, file: StaticString = #filePath, line: UInt = #line) throws {
    let screenshot = XCUIScreen.main.screenshot()
    let env = ProcessInfo.processInfo.environment
    guard let root = env["VISUAL_OUTPUT_DIR"] else {
        XCTFail("VISUAL_OUTPUT_DIR is missing", file: file, line: line)
        return
    }
    let url = URL(fileURLWithPath: root).appendingPathComponent("\(id).png")
    try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
    try screenshot.pngRepresentation.write(to: url, options: .atomic)

    let attachment = XCTAttachment(screenshot: screenshot)
    attachment.name = "visual.\(id)"
    attachment.lifetime = .keepAlways
    add(attachment)
}
```

- [ ] `reusable-macos-e2e.yml` pins `runs-on: macos-26` and sets `DEVELOPER_DIR=/Applications/Xcode_26.6.app/Contents/Developer` by default.
- [ ] Create `artifacts/visual/current` and export `VISUAL_OUTPUT_DIR` before tests.
- [ ] Run `xcodebuild build-for-testing`, then `test-without-building`, using explicit project/workspace, scheme, destination, optional test plan, DerivedData path, and result bundle.
- [ ] Always export all `.xcresult` attachments for diagnostics with:

```bash
xcrun xcresulttool export attachments \
  --path "$RUNNER_TEMP/e2e.xcresult" \
  --output-path "$RUNNER_TEMP/e2e-attachments"
```

PNG comparison uses direct `VISUAL_OUTPUT_DIR` files; `.xcresult` attachments are diagnostic redundancy.
- [ ] `collect-metadata.sh` emits `profile.json` containing schemaVersion, profile id, RUNNER_OS, RUNNER_ARCH, `xcodebuild -version`, DEVELOPER_DIR, locale, language, timezone, and current SHA.
- [ ] Upload current PNG capture artifact + profile metadata; upload `.xcresult` + attachments with `if: always()` and 14-day retention.
- [ ] Permissions are `contents: read` only; no Environment or release secrets.
- [ ] Run actionlint/zizmor/ShellCheck/shfmt.
- [ ] Commit: `feat: add standard macOS E2E workflow`.

---

### Task 7: Hybrid visual regression workflow

**Files:**
- Create `.github/workflows/reusable-visual-regression.yml`
- Create `.github/workflows/visual-regression.yml`

**Stable final check:** `Visual Regression / Compare UI`.

**Caller configuration:** `visual-regression.yml` reads repository variables. If `VISUAL_REGRESSION_ENABLED != true`, capture/compare are skipped and the final gate clearly reports `NOT CONFIGURED`; documentation forbids requiring it until configured.

- [ ] Capture job calls Task 6 reusable E2E and produces exact current artifact name.
- [ ] Compare job downloads current captures and validates manifest before baseline resolution.
- [ ] Git cases use checked-in `Tests/VisualBaselines`; missing Git PNG fails.
- [ ] If manifest contains rolling cases, resolve exact rolling artifact through Task 3 using workflow `visual-regression.yml` and successful `main` only.
- [ ] Validate current `profile.json` against manifest profile; validate rolling `profile.json` against current profile before rolling comparisons.
- [ ] Invoke Task 2 `compare-manifest` with current SHA, baseline run id, and bootstrap flag.
- [ ] Always upload `visual-report` with 14-day retention and write `$GITHUB_STEP_SUMMARY` table: Case, Baseline, Changed pixels, Ratio, Max delta, Status.
- [ ] On successful trusted `main` push only, publish current rolling case PNGs plus `profile.json` as the exact rolling artifact name, retention 90 days. PR artifacts are never baseline candidates.
- [ ] Final gate uses `if: always()` and fails on capture/compare failure; bootstrap is reported explicitly.
- [ ] Use concurrency cancellation for superseded PR commits.
- [ ] Run actionlint and zizmor.
- [ ] Commit: `feat: add hybrid visual regression workflow`.

---

### Task 8: Template self-tests

**Files:**
- Create `.github/workflows/test-infrastructure.yml`
- Modify `.github/workflows/quality.yml` only if recursive shell checks do not already cover new scripts.

**Stable check:** `Test Infrastructure / Generic tooling`.

- [ ] Path-trigger this workflow for `Tools/VisualDiff/**`, `scripts/ci/**`, `scripts/test/**`, `scripts/visual/**`, new test/visual workflows, and example manifests.
- [ ] On `macos-26`, set pinned Xcode and run `swift test --package-path Tools/VisualDiff`.
- [ ] Run `python3 -m unittest scripts/test/test-compare-coverage.py -v`.
- [ ] Run `bash scripts/ci/test-resolve-trusted-main-artifact.sh`.
- [ ] Run manifest validation smoke command against `visual-regression.example.json`.
- [ ] Existing Ubuntu Quality continues actionlint, zizmor, ShellCheck, shfmt, secret scan, and Homebrew smoke tests.
- [ ] Verify all new workflows through actionlint/zizmor and all shell through ShellCheck/shfmt.
- [ ] Commit: `ci: add generic test infrastructure validation`.

---

### Task 9: Documentation and contributor policy

**Files:**
- Create `docs/TESTING.md`
- Create `docs/VISUAL_REGRESSION.md`
- Modify `README.md`
- Modify `CONTRIBUTING.md`
- Modify `.github/pull_request_template.md`
- Modify `.github/CODEOWNERS`

- [ ] Document unit/integration adapters and repository variables required to enable `tests.yml`.
- [ ] Document app test mode: temporary data dir, deterministic fixture injection, network fake, clock/random seed, animations, explicit appearance.
- [ ] Require stable accessibility identifiers rather than localized text or coordinates.
- [ ] Document the `recordVisual` helper contract and direct PNG + XCTAttachment behavior.
- [ ] Document Git-baseline update: capture under canonical profile -> inspect report -> replace reviewed PNG -> commit with UI change.
- [ ] Document rolling baseline bootstrap, 90-day retention expiry behavior, trusted-main advancement, and profile migration.
- [ ] Document privileged system E2E as separate protected test Environment/runner and explicitly forbid `release` Environment reuse.
- [ ] PR template adds checks for tests, E2E, visual report, intentional baseline changes, and accessibility ids.
- [ ] CODEOWNERS adds:

```text
/Tests/VisualBaselines/ @Lamy210
/.github/workflows/*test*.yml @Lamy210
/.github/workflows/*visual*.yml @Lamy210
/Tools/VisualDiff/ @Lamy210
```

- [ ] Commit: `docs: document test and visual regression workflow`.

---

### Task 10: Final verification and merge PR #2

- [ ] Run:

```bash
swift test --package-path Tools/VisualDiff
python3 -m unittest scripts/test/test-compare-coverage.py -v
bash scripts/ci/test-resolve-trusted-main-artifact.sh
find scripts -type f -name '*.sh' -print0 | xargs -0 shellcheck
shfmt -d -i 2 -ci scripts
actionlint
zizmor .github/workflows
```

- [ ] Review workflow permissions. Ordinary test/visual jobs must not introduce `pull_request_target`, `secrets: inherit`, `environment: release`, `contents: write`, or `pull-requests: write`.
- [ ] Compare `main...HEAD`; only planned tooling/workflow/test/doc files may differ.
- [ ] Latest PR head must show green: Repository hygiene, GitHub Actions security, Secret scan, Swift Quality, Test Infrastructure.
- [ ] Resolve review threads.
- [ ] Mark ready and squash-merge with expected head SHA.
- [ ] Verify post-merge `main` CI is green before claiming the template phase complete.

---

### Task 11: Real adopter validation (separate repository PR)

**Recommended first target:** inspect `Lamy210/SchneeBar` and `Lamy210/SchneeGlass`, then choose the one whose current Xcode test topology makes the smallest representative adoption.

- [ ] Inspect actual scheme/test plan/targets/accessibility ids/current CI; do not guess names.
- [ ] Add one secret-free critical-flow XCUITest using deterministic app test mode.
- [ ] Capture at least two cases via `recordVisual`: one Git baseline and one rolling-main baseline.
- [ ] Configure both cases in one manifest.
- [ ] Demonstrate failure by a temporary test-only UI variation, verify expected/actual/diff/report artifact, then revert that variation.
- [ ] Demonstrate coverage ratchet: unchanged/improved passes; substantive decrease fails.
- [ ] Merge adopter PR only after its own required checks are green.

This closes the design acceptance criteria with a real `.app` rather than only template fixtures.
