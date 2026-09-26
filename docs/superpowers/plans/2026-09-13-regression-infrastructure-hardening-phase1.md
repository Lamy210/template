# Regression Infrastructure Hardening Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the existing visual-regression foundation so intentional UI changes, rolling baselines, profile identity, and the final required check have explicit, testable trust semantics before coverage and XCUITest workflows are added.

**Architecture:** Keep pixel comparison in `VisualDiffCore`, but add independent policy units for content digests, controlled-profile identity, approval validation, bundle validation, and rolling-case state. A shell resolver selects only successful `main` push artifacts and performs safe archive extraction. A small Required Gate decision tool turns internal job outcomes into one stable Ruleset-facing result.

**Tech Stack:** Swift 6, Swift Package Manager, Foundation, CryptoKit, CoreGraphics/ImageIO, XCTest, Bash, Python 3 standard library, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-13-regression-infrastructure-hardening-design.md`

## Global Constraints

- Public pull-request code remains secret-free and cannot execute on privileged runners.
- Rolling baselines may originate only from the current repository, expected workflow, `event=push`, `head_branch=main`, `conclusion=success`, exact artifact name, and a non-expired artifact.
- Approval records authorize one exact `(caseID, fromDigest, toDigest, profileFingerprint)` tuple only.
- Git baseline updates remain source-controlled; approval records primarily solve rolling-baseline merge deadlock.
- Controlled-profile mismatch prevents pixel comparison. Observed-runtime drift is diagnostic only.
- Established rolling cases cannot silently bootstrap again. New rolling cases may bootstrap only when absent from the previous trusted bundle case index.
- Archive extraction rejects absolute members, traversal, duplicate canonical paths, and escaping symlinks.
- Required Ruleset integration exposes one stable `Tests / Required Gate` check; internal jobs remain separately diagnosable.
- Existing Quality, Swift Quality, ShellCheck, shfmt, actionlint, zizmor, and Gitleaks gates must remain green.
- No third-party runtime package is added for hashing, JSON, ZIP validation, or gate decisions.

## File Structure

```text
Tools/VisualDiff/Sources/VisualDiffCore/
  ContentDigest.swift
  ControlledProfile.swift
  VisualApproval.swift
  BaselineBundle.swift
  ManifestRunner.swift
Tools/VisualDiff/Tests/VisualDiffCoreTests/
  ContentDigestTests.swift
  ControlledProfileTests.swift
  VisualApprovalTests.swift
  BaselineBundleTests.swift
  ManifestRunnerTests.swift

scripts/ci/
  resolve-trusted-main-artifact.sh
  test-resolve-trusted-main-artifact.sh
  required-gate.py
  test-required-gate.py

Tests/VisualRegression/Approvals/.gitkeep
```

---

### Task 1: Restore repository quality gates

**Files:**
- Modify Swift files under `Tools/VisualDiff/**` only where SwiftFormat reports differences.
- Modify `scripts/ci/test-resolve-trusted-main-artifact.sh` only where shfmt reports differences.

**Interfaces:** No runtime behavior change. This task restores the pre-existing repository formatting contract before functional hardening continues.

- [ ] Run the exact CI format checks against the current branch state.
- [ ] Confirm SwiftFormat failures are formatting-only and shfmt failure is indentation-only.
- [ ] Apply SwiftFormat 0.63.0 output without changing test expectations or public APIs.
- [ ] Apply `shfmt -w -i 2 -ci scripts/ci/test-resolve-trusted-main-artifact.sh`.
- [ ] Run VisualDiff tests, SwiftFormat lint, SwiftLint, ShellCheck, shfmt, actionlint, and zizmor.
- [ ] Commit `style: align regression infrastructure with repository formatters`.

---

### Task 2: Trusted-main artifact resolver

**Files:**
- Create `scripts/ci/resolve-trusted-main-artifact.sh`.
- Modify `scripts/ci/test-resolve-trusted-main-artifact.sh`.

**Interface:**

```text
resolve-trusted-main-artifact.sh \
  --repository owner/repo \
  --workflow workflow.yml \
  --artifact exact-name \
  --output directory
```

On success it writes validated artifact contents into `--output` and writes `resolver-metadata.json` containing repository, workflow, run ID, run attempt, source SHA, artifact ID, artifact name, artifact digest when exposed, and retrieval time. Exit code `4` means no trusted candidate exists; all unsafe/malformed states use other non-zero codes.

- [ ] Extend RED fixtures so accepted run JSON includes `id`, `run_attempt`, `head_sha`, `head_repository.full_name`, `event=push`, `head_branch=main`, and `conclusion=success`; artifact JSON includes exact `name`, `expired=false`, and optional `digest`.
- [ ] Add RED cases for wrong `head_repository`, malformed JSON, duplicate exact-name artifacts, absolute ZIP member, `..` ZIP member, duplicate canonical ZIP member, and escaping symlink.
- [ ] Run `bash scripts/ci/test-resolve-trusted-main-artifact.sh`; verify failure because resolver is absent.
- [ ] Implement argument validation and require `GH_TOKEN` plus `gh`, `python3`, and `unzip`/Python ZIP support.
- [ ] Query only the expected workflow's successful `main` push runs, then revalidate every trust field client-side.
- [ ] Select the newest trusted run that contains exactly one non-expired exact-name artifact; never fall back to PR/manual/non-main runs.
- [ ] Download ZIP to a fresh temporary directory.
- [ ] Validate ZIP members with Python `zipfile`: reject absolute paths, drive-prefixed paths, `..`, duplicate canonical paths, and symlink entries whose resolved target escapes the extraction root.
- [ ] Extract only after validation and atomically replace the requested output directory.
- [ ] Write `resolver-metadata.json` with provenance fields; preserve GitHub artifact digest when present.
- [ ] Run resolver tests, ShellCheck, and shfmt; verify GREEN.
- [ ] Commit `feat: harden trusted main artifact resolution`.

---

### Task 3: Deterministic content digests and controlled-profile fingerprint

**Files:**
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ContentDigest.swift`.
- Create `Tools/VisualDiff/Sources/VisualDiffCore/ControlledProfile.swift`.
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/ContentDigestTests.swift`.
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/ControlledProfileTests.swift`.

**Interfaces:**

```swift
public enum ContentDigest {
    public static func sha256(data: Data) -> String
    public static func sha256(fileURL: URL) throws -> String
}

public struct ControlledProfile: Codable, Sendable, Equatable {
    public let runnerFamily: String
    public let architecture: String
    public let xcodePolicy: String
    public let locale: String
    public let language: String
    public let timezone: String
    public let appearance: String
    public let displayScale: Double
    public let captureGeometry: String
    public let fixtureVersion: String
    public let captureContractVersion: Int
    public let comparatorSchemaVersion: Int

    public func fingerprint() throws -> String
}
```

- [ ] Write RED digest tests using known SHA-256 vectors for empty data and `abc`, plus file/data equality.
- [ ] Write RED fingerprint tests proving property-value changes change the fingerprint while repeated encoding of identical values is stable.
- [ ] Run `swift test --package-path Tools/VisualDiff`; verify RED.
- [ ] Implement SHA-256 with CryptoKit and return lowercase `sha256:<64-hex>` strings.
- [ ] Implement a dedicated canonical JSON encoder for `ControlledProfile`: sorted keys, deterministic UTF-8, finite numeric values only.
- [ ] Hash canonical JSON using `ContentDigest`.
- [ ] Run unit tests and Swift quality checks; verify GREEN.
- [ ] Commit `feat: add regression content and profile identities`.

---

### Task 4: Exact visual-change approvals

**Files:**
- Create `Tools/VisualDiff/Sources/VisualDiffCore/VisualApproval.swift`.
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/VisualApprovalTests.swift`.
- Create `Tests/VisualRegression/Approvals/.gitkeep`.
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`.
- Modify `Tools/VisualDiff/Tests/VisualDiffCoreTests/ManifestRunnerTests.swift`.

**Interfaces:**

```swift
public struct VisualApproval: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let caseID: String
    public let fromDigest: String
    public let toDigest: String
    public let profileFingerprint: String
    public let reason: String

    public func validates(
        caseID: String,
        fromDigest: String,
        toDigest: String,
        profileFingerprint: String
    ) -> Bool
}
```

`VisualCaseStatus` becomes `passed`, `failed`, `approvedChange`, or `bootstrap`.

- [ ] Write RED tests: exact tuple validates; changed case/from/to/profile fails; blank reason fails decoding/validation; unsupported schema fails.
- [ ] Write RED ManifestRunner test where a rolling comparison differs but exact approval produces `approvedChange` and still emits expected/actual/diff/report artifacts.
- [ ] Write RED test proving a one-byte later image change invalidates the previous approval.
- [ ] Run VisualDiff tests; verify RED.
- [ ] Implement approval decoding/validation with approval paths confined to `Tests/VisualRegression/Approvals`.
- [ ] Compute trusted expected/current image digests before evaluating approval.
- [ ] Preserve `failed` when no exact approval matches; never alter pixel metrics because an approval exists.
- [ ] Include approval identity and reason in `report.json` only when status is `approvedChange`.
- [ ] Run tests and Swift quality checks; verify GREEN.
- [ ] Commit `feat: add digest-bound visual change approvals`.

---

### Task 5: Baseline bundle manifest and case-level bootstrap

**Files:**
- Create `Tools/VisualDiff/Sources/VisualDiffCore/BaselineBundle.swift`.
- Create `Tools/VisualDiff/Tests/VisualDiffCoreTests/BaselineBundleTests.swift`.
- Modify `Tools/VisualDiff/Sources/VisualDiffCore/ManifestRunner.swift`.
- Modify `Tools/VisualDiff/Tests/VisualDiffCoreTests/ManifestRunnerTests.swift`.

**Interfaces:**

```swift
public struct BaselineBundleManifest: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let sourceRepository: String
    public let workflow: String
    public let sourceRunID: String
    public let runAttempt: Int
    public let sourceSHA: String
    public let profileFingerprint: String
    public let cases: [String: String] // case id -> sha256 digest
}

public enum BaselineBundleValidator {
    public static func validate(
        root: URL,
        manifest: BaselineBundleManifest,
        expectedProfileFingerprint: String
    ) throws
}
```

- [ ] Write RED tests for valid bundle, missing image, digest mismatch, unexpected profile fingerprint, invalid case ID/path, duplicate JSON case keys detected before decode, and case index membership.
- [ ] Write RED runner tests: established A/B/C missing baseline fails; newly introduced D absent from previous case index becomes `bootstrap`; first-ever bundle absence may bootstrap only under explicit repository bootstrap mode.
- [ ] Run tests; verify RED.
- [ ] Implement strict bundle layout `bundle-manifest.json`, `profile.json`, `images/<case-id>.png` and validate every declared image digest.
- [ ] Reject case IDs that are empty or unsafe as file names.
- [ ] Replace global rolling bootstrap semantics for established repositories with previous-bundle case-index logic.
- [ ] Keep repository-wide bootstrap only for no-prior-baseline and explicit profile migration modes.
- [ ] Run tests and Swift quality; verify GREEN.
- [ ] Commit `feat: validate rolling baseline bundles and case bootstrap`.

---

### Task 6: Stable Required Gate decision engine

**Files:**
- Create `scripts/ci/required-gate.py`.
- Create `scripts/ci/test-required-gate.py`.
- Later caller workflows consume this tool; this task does not yet add XCUITest or coverage workflows.

**Input schema:**

```json
{
  "schemaVersion": 1,
  "checks": [
    {"name": "Unit", "required": true, "result": "success"},
    {"name": "E2E", "required": false, "result": "not-applicable"},
    {"name": "Visual", "required": true, "result": "approved-change"}
  ]
}
```

Allowed results: `success`, `approved-change`, `bootstrap`, `not-applicable`, `disabled`, `failure`, `cancelled`, `missing`, `unsafe`.

- [ ] Write RED tests showing required success/approved-change pass, optional not-applicable passes, required failure/cancelled/missing/unsafe fail, and required bootstrap fails unless input explicitly marks `allowBootstrap=true` for that check.
- [ ] Run `python3 -m unittest scripts/ci/test-required-gate.py -v`; verify RED.
- [ ] Implement strict schema validation with Python standard library only.
- [ ] Print one deterministic summary line per check and exit `0` only when all required checks satisfy policy.
- [ ] Add JSON summary output option for later `$GITHUB_STEP_SUMMARY` integration.
- [ ] Run Python tests and static syntax check; verify GREEN.
- [ ] Commit `feat: add stable regression required gate policy`.

---

### Task 7: Phase-1 integration and documentation sync

**Files:**
- Modify `.github/workflows/test-infrastructure.yml`.
- Modify `docs/superpowers/plans/2026-09-13-test-e2e-visual-regression-implementation.md` to reference the hardening phase.
- Modify PR #2 title/body after checks are green.

**Interfaces:** `Test Infrastructure / Generic tooling` remains the self-test job for the template and now runs VisualDiff tests, manifest smoke validation, trusted resolver tests, and Required Gate tests.

- [ ] Add resolver and Required Gate test commands to `test-infrastructure.yml` without widening token permissions beyond what the tests need.
- [ ] Ensure the workflow itself uses no top-level path behavior that would later be copied as a required Ruleset check without an aggregator.
- [ ] Run actionlint and zizmor.
- [ ] Run exact branch CI: Quality, Swift Quality, Test Infrastructure.
- [ ] Update the original implementation plan so coverage/E2E tasks depend on this hardening phase rather than duplicating old bootstrap/profile assumptions.
- [ ] Update PR #2 summary from design-only language to implemented regression-foundation language while keeping it Draft until later coverage/E2E phases are complete.
- [ ] Commit `docs: align regression foundation plan after hardening`.

## Phase-1 Completion Gate

Before moving to coverage or XCUITest implementation, all of the following must be true on the exact feature-branch head:

```text
Quality / Repository hygiene       success
Quality / GitHub Actions security success
Quality / Secret scan             success
Swift Quality / Swift quality     success
Test Infrastructure / Generic tooling success
```

Additionally:

- VisualDiff tests cover digest/profile/approval/bundle/bootstrap policy.
- Resolver tests cover trusted provenance and hostile archive fixtures.
- Required Gate tests cover all allowed result states.
- No formatter/linter exception is added merely to make the new code pass.
