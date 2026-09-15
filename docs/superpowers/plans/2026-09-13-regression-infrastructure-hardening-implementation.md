# Regression Infrastructure Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing macOS regression foundation so intentional UI changes, rolling baselines, coverage baselines, fork PRs, and required checks remain trustworthy and operable over time.

**Architecture:** Keep capture, comparison, provenance, approval, and policy evaluation as separate contracts. Extend `VisualDiffCore` with digest-bound approval/profile/bundle models, use one trusted-main resolver for rolling visual and coverage data, and aggregate all configured test subsystems behind one stable `Tests / Required Gate` check.

**Tech Stack:** Swift 6, SwiftPM, Foundation, CryptoKit, CoreGraphics/ImageIO, XCTest/XCUITest, Bash, Python 3 standard library, GitHub Actions.

**Specs:**
- `docs/superpowers/specs/2026-09-13-test-e2e-visual-regression-design.md`
- `docs/superpowers/specs/2026-09-13-regression-infrastructure-hardening-design.md`

## Global Constraints

- Public/fork PR code is untrusted and never receives release, production, notarization, or privileged-runner credentials.
- Rolling visual and coverage baselines are accepted only from successful `push` runs on `main` of the expected workflow in the current repository.
- Visual approval records are exact identity records, not wildcard suppressions.
- Controlled-profile mismatch forbids pixel comparison; observed-runtime drift is diagnostic only.
- Existing established rolling cases cannot silently bootstrap again.
- Required workflows always produce a stable final result; do not rely on top-level `paths:` filters for required checks.
- Existing Quality, Swift Quality, actionlint, zizmor, ShellCheck, shfmt, Gitleaks, and release trust boundaries must remain green.
- Every production change follows RED → GREEN → full regression verification.

---

### Task 1: Exact visual-change approval model

**Files:**
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ImageDigest.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/VisualApproval.swift`
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/ComparisonReport.swift`
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/VisualManifest.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/VisualApprovalTests.swift`
- Modify `Tools/VisualDiff/Tests/VisualDiffCoreTests/ManifestRunnerTests.swift`

**Interfaces:**

```swift
public enum ImageDigest {
    public static func sha256(_ data: Data) -> String
    public static func sha256(fileAt url: URL) throws -> String
}

public struct VisualApproval: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let caseID: String
    public let fromDigest: String
    public let toDigest: String
    public let profileFingerprint: String
    public let reason: String

    public static func load(from url: URL) throws -> VisualApproval
}

public enum VisualCaseStatus: String, Codable, Sendable {
    case passed
    case failed
    case approvedChange = "approved-change"
    case bootstrap
}
```

- [ ] Add RED tests proving an exact approval changes a failing rolling case to `approved-change`.
- [ ] Add RED tests proving wrong case ID, old baseline digest, changed current digest, wrong profile fingerprint, empty reason, unsupported schema version, absolute approval path, and `..` approval path are rejected.
- [ ] Run `swift test --package-path Tools/VisualDiff`; expect RED due missing approval/digest APIs.
- [ ] Implement SHA-256 using CryptoKit and normalize the external representation to lowercase `sha256:<64 hex>`.
- [ ] Implement approval decoding/validation under `Tests/VisualRegression/Approvals/` only.
- [ ] Extend manifest cases with optional `approval` path; rolling cases may use it, Git cases continue to prefer checked-in baseline PNG updates.
- [ ] Extend runner evaluation: a pixel mismatch remains `failed` unless every approval identity field exactly matches baseline digest, actual digest, case ID, and current controlled profile fingerprint.
- [ ] Preserve comparison metrics and expected/actual/diff artifacts for `approved-change` cases.
- [ ] Run Swift tests and verify GREEN.
- [ ] Run SwiftFormat/SwiftLint checks before moving on.

---

### Task 2: Controlled profile fingerprint and observed runtime split

**Files:**
- Replace/extend `Tools/VisualDiff/Sources/VisualDiffCore/ProfileMetadata.swift`
- Create `Tools/VisualDiff/Sources/VisualDiffCore/CanonicalJSON.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/ProfileMetadataTests.swift`
- Modify `scripts/visual/collect-metadata.sh` when it exists/lands.

**Interfaces:**

```swift
public struct ControlledProfile: Codable, Equatable, Sendable {
    public let runnerFamily: String
    public let architecture: String
    public let xcodePolicy: String
    public let locale: String
    public let language: String
    public let timezone: String
    public let appearance: String
    public let displayScale: String
    public let captureGeometry: String
    public let fixtureVersion: String
    public let captureContractVersion: Int
    public let comparatorSchemaVersion: Int

    public var fingerprint: String { get }
}

public struct ObservedRuntime: Codable, Equatable, Sendable {
    public let macOSBuild: String
    public let runnerImageVersion: String
    public let xcodeBuild: String
}
```

- [ ] Add RED tests that canonical key ordering produces the same fingerprint and any controlled field change changes the fingerprint.
- [ ] Add RED tests showing observed-runtime-only drift does not change the fingerprint.
- [ ] Run tests and verify RED.
- [ ] Implement deterministic canonical JSON encoding with sorted keys and SHA-256 fingerprinting.
- [ ] Migrate runner profile checks from mutable profile ID equality to controlled fingerprint equality.
- [ ] Keep human-readable profile ID as report metadata only.
- [ ] Run tests and quality checks; verify GREEN.

---

### Task 3: Trusted-main artifact resolver with provenance and safe extraction

**Files:**
- Create `scripts/ci/resolve-trusted-main-artifact.sh`
- Modify `scripts/ci/test-resolve-trusted-main-artifact.sh`

**Interface:**

```text
resolve-trusted-main-artifact.sh \
  --repository owner/repo \
  --workflow workflow.yml \
  --artifact exact-name \
  --output directory
```

**Required emitted metadata:**

```text
run_id
run_attempt
head_sha
workflow_id
artifact_id
artifact_name
artifact_digest (when provided)
```

- [ ] Keep the existing RED `resolver missing` test and expand fixtures for repo identity, workflow identity, main/push/success, expiration, exact name, and digest capture.
- [ ] Add RED ZIP fixtures for absolute member, `..`, duplicate canonical path, and escaping symlink.
- [ ] Run `bash scripts/ci/test-resolve-trusted-main-artifact.sh`; verify RED.
- [ ] Implement fixed GitHub API endpoint usage through `gh api`; never accept arbitrary download URLs.
- [ ] Revalidate response fields even when query filters request main/push/success.
- [ ] Select only exact non-expired artifact names from the selected trusted run.
- [ ] Validate archive members using Python stdlib before extraction; reject absolute/traversal/duplicate paths and symlink entries.
- [ ] Extract into a newly created directory only after validation.
- [ ] Write provenance JSON next to extracted data.
- [ ] Run resolver tests, ShellCheck, shfmt; verify GREEN.

---

### Task 4: Self-describing baseline bundle and file digest validation

**Files:**
- Create `Tools/VisualDiff/Sources/VisualDiffCore/BaselineBundle.swift`
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/BaselineBundleTests.swift`
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`
- Modify `Tools/VisualDiff/Sources/visual-diff/main.swift`

**Interfaces:**

```swift
public struct BaselineBundleManifest: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let repository: String
    public let workflow: String
    public let sourceRunID: String
    public let runAttempt: Int
    public let sourceCommitSHA: String
    public let profileFingerprint: String
    public let previousBaselineReference: String?
    public let files: [String: String]
}
```

- [ ] Add RED tests for valid bundle, missing listed file, extra unexpected image in strict mode, changed PNG digest, duplicate case mapping, and profile mismatch.
- [ ] Implement bundle decoding and strict per-file SHA-256 verification.
- [ ] Make rolling comparison read only validated bundle files; never arbitrary resolver output paths.
- [ ] Include source run/artifact/bundle provenance in per-case reports.
- [ ] Run tests and quality checks; verify GREEN.

---

### Task 5: Case-level bootstrap semantics

**Files:**
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/BaselineBundle.swift`
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`
- Modify `Tools/VisualDiff/Tests/VisualDiffCoreTests/ManifestRunnerTests.swift`

- [ ] Add RED tests for previous cases A/B/C plus current A/B/C/D: D may bootstrap, missing A/B/C must fail.
- [ ] Add RED test that repository-wide bootstrap is permitted only when no previous trusted bundle exists or explicit profile migration mode is active.
- [ ] Implement previous case-index evaluation before resolving per-case images.
- [ ] Preserve `bootstrap` as distinct from `passed` and `approved-change`.
- [ ] Run tests; verify GREEN.

---

### Task 6: Coverage schema/profile and raw-count ratchet

**Files:**
- Create `scripts/test/export-coverage.sh`
- Create `scripts/test/compare-coverage.py`
- Create `scripts/test/test-compare-coverage.py`

**Schema:**

```json
{
  "schemaVersion": 1,
  "coverageProfileFingerprint": "sha256:...",
  "totals": {
    "coveredLines": 8010,
    "executableLines": 10000,
    "lineCoverage": 0.801
  },
  "targets": {}
}
```

- [ ] RED tests: equal passes; tiny configured tolerance passes; substantive regression fails; profile mismatch returns migration-required; denominator/raw-count changes are reported; malformed or impossible counts fail.
- [ ] Implement Python `decimal.Decimal` comparison and strict schema validation.
- [ ] Implement Xcode `xccov` normalizer and SwiftPM LLVM coverage normalizer.
- [ ] Include coverage profile inputs in a deterministic SHA-256 fingerprint.
- [ ] Run unittest, ShellCheck, shfmt; verify GREEN.

---

### Task 7: Stable `Tests / Required Gate` policy engine

**Files:**
- Create `scripts/test/evaluate-required-gate.py`
- Create `scripts/test/test-evaluate-required-gate.py`
- Create/modify `.github/workflows/tests.yml`
- Create/modify `.github/workflows/reusable-swift-tests.yml`

**Input contract:** each subsystem reports `success`, `failure`, `not-applicable`, or `disabled`, plus whether it is configured as required.

- [ ] RED tests: required success passes; required failure fails; unexpected cancelled/missing fails; optional failure is visible but non-blocking; required not-applicable is accepted only when classifier explicitly marks it not-applicable; disabled required subsystem is configuration error.
- [ ] Implement policy evaluator.
- [ ] Make caller workflow always start; avoid top-level path filters for the required workflow.
- [ ] Add a lightweight classifier job and internal Unit/Integration/E2E/Visual/Coverage results.
- [ ] Add final job named exactly `Tests / Required Gate` with `if: always()` and no secrets.
- [ ] Run actionlint/zizmor plus policy tests; verify GREEN.

---

### Task 8: Standard macOS E2E determinism and visual capture contract

**Files:**
- Create/modify `.github/workflows/reusable-macos-e2e.yml`
- Create `docs/TESTING.md`
- Create `docs/VISUAL_REGRESSION.md`
- Update `CONTRIBUTING.md`

- [ ] Pin `macos-26` and Xcode 26.6 for canonical visual capture.
- [ ] Use deterministic launch environment for fixture directory, clock/seed, locale/timezone, animation policy, appearance, and `VISUAL_OUTPUT_DIR`.
- [ ] Document app readiness synchronization through stable accessibility identifiers instead of fixed sleeps.
- [ ] Prefer `XCUIElement.screenshot()`/window screenshot over full desktop for canonical captures.
- [ ] Always upload `.xcresult` and visual diagnostics on failure with 14-day retention.
- [ ] Keep privileged/TCC E2E entirely separate from fork PR execution.
- [ ] Run actionlint/zizmor and documentation consistency checks.

---

### Task 9: Rolling baseline publication and retention refresh

**Files:**
- Create/modify `.github/workflows/visual-regression.yml`
- Create/modify `.github/workflows/reusable-visual-regression.yml`

- [ ] PR flow resolves trusted old baseline, validates bundle/profile, compares, and accepts only `passed`, exact `approved-change`, or legitimate `bootstrap`.
- [ ] Main flow publishes a new bundle only after all required regression policy succeeds.
- [ ] Add scheduled refresh that re-captures current main, compares first, and republishes only on policy success.
- [ ] A missing old baseline outside explicit bootstrap/migration fails rather than silently reseeding.
- [ ] Use least privilege: `contents: read`, `actions: read` only where baseline lookup needs it.
- [ ] Add concurrency cancellation for superseded PR visual runs.
- [ ] Run actionlint/zizmor; verify GREEN.

---

### Task 10: Template fixture macOS app and end-to-end self-test

**Files:**
- Create `Fixtures/MacTestApp/` Xcode project/source/tests
- Modify template test workflows to exercise the fixture

- [ ] Create one-window fixture app with deterministic label and button state transition, stable accessibility identifiers, no network, and no special entitlements.
- [ ] Add unit test, XCUITest flow, readiness marker, Light/Dark captures, and coverage.
- [ ] Run `build-for-testing` then `test-without-building` on the canonical runner.
- [ ] Feed captured PNGs through VisualDiff and coverage through ratchet tooling.
- [ ] Prove an intentionally modified fixture capture produces expected/actual/diff/report diagnostics in a dedicated negative self-test.
- [ ] Run all template CI; verify GREEN.

---

### Task 11: Repository governance, documentation, and adopter validation

**Files:**
- Update `README.md`
- Update `docs/SETUP.md`
- Update `.github/CODEOWNERS`
- Update `.github/pull_request_template.md`
- Update PR #2 title/body before review

- [ ] Document optional CODEOWNERS protection for approvals/baselines in Team mode.
- [ ] Document only `Tests / Required Gate` as the test Ruleset requirement once configured.
- [ ] Document exact visual approval flow, profile migration, case bootstrap, baseline recovery, and retention refresh.
- [ ] Apply the template contract to one real macOS adopter (SchneeBar preferred unless repository state suggests SchneeGlass is a safer first consumer).
- [ ] Verify unit/integration, Standard E2E, Git baseline, rolling baseline, intentional approved change, failure diff artifact, and coverage regression behavior.
- [ ] Keep privileged E2E optional until an adopter has a concrete TCC-required scenario.
- [ ] Run final exact-head Quality, Swift Quality, Test Infrastructure, and all new tests.
- [ ] Mark PR #2 ready only after exact-head checks are green; squash merge with expected head SHA.
