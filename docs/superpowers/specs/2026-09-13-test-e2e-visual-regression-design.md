# Test, E2E, and Visual Regression Foundation Design

Date: 2026-09-13
Status: Draft for review

## 1. Purpose

Extend the macOS development template with a reusable test architecture covering unit tests, integration tests, end-to-end tests, coverage regression checks, and UI visual regression.

The design must preserve the existing trust model: pull-request test jobs are secret-free by default, while privileged system tests that require special macOS permissions or external test credentials are isolated from ordinary PR validation.

Visual regression uses a hybrid baseline model:

1. **Git baselines** for stable and critical UI states that should be reviewed as source changes.
2. **Rolling main artifacts** for large, dynamic, or environment-sensitive UI captures that are expensive or noisy to keep permanently in Git.

The comparison contract is image-based and tool-agnostic. Application code may use XCUITest, XCTest, Swift Testing, SnapshotTesting, SwiftUI rendering, or another adapter to produce PNG files, but CI owns baseline selection, comparison, reporting, and pass/fail policy.

## 2. Goals

- Standardize unit, integration, E2E, and visual-regression workflows for macOS apps.
- Make required PR tests deterministic, secret-free, and suitable for fork contributions.
- Keep test execution independent from signing/notarization credentials.
- Support both Xcode projects/workspaces and Swift Package Manager where practical.
- Produce actionable failure artifacts rather than only a red CI status.
- Provide coverage regression protection using a main-branch baseline/ratchet model.
- Detect UI regressions through reproducible PNG comparisons.
- Allow reviewers to inspect expected, actual, and diff images for changed UI.
- Support stable Git-backed visual baselines and rolling main-run baselines in the same repository.
- Separate ordinary GitHub-hosted E2E from privileged macOS-system E2E that needs TCC permissions.
- Keep third-party snapshot libraries optional rather than making them part of the core contract.
- Keep CI permissions least-privilege and avoid PR-writing permissions for ordinary test reporting.

## 3. Non-goals for the first implementation

- Automatically approving or updating visual baselines from CI.
- Running release credentials inside test jobs.
- Requiring live production services for PR integration tests.
- Treating flaky retries as a passing test policy.
- Providing full virtualization of every macOS security/TCC permission on GitHub-hosted runners.
- Supporting iOS/tvOS/watchOS visual regression in the initial macOS template.
- Building a hosted visual-diff SaaS.
- Replacing XCTest/XCUITest with a custom test framework.

## 4. Test pyramid and required gates

The template defines four independent layers.

```text
Pull Request
   |
   +-- Unit tests
   |     `-- pure domain/component behavior
   |
   +-- Integration tests
   |     `-- persistence / IPC / repository / service boundaries
   |
   +-- E2E tests
   |     `-- launch real .app and exercise critical user flows
   |
   `-- Visual regression
         +-- Git baseline cases
         `-- rolling-main baseline cases
```

Each layer must have its own CI step or job result so failures remain diagnosable.

### 4.1 Unit tests

Purpose:

- validate domain logic and deterministic components;
- run quickly on every relevant PR;
- generate code coverage when supported.

Supported adapters:

- Xcode/XCTest or Swift Testing via `xcodebuild test`;
- Swift Package Manager via `swift test`.

Unit tests must not depend on network services, release credentials, or user-specific machine state.

### 4.2 Integration tests

Purpose:

- verify boundaries between application components;
- validate persistence, serialization, IPC, filesystem adapters, database adapters, and local service integrations;
- remain deterministic and reproducible in CI.

External systems should be replaced by local fixtures, mocks, in-memory adapters, local containers, or deterministic fake services when feasible.

PR integration tests remain secret-free. Tests that genuinely require a third-party test account belong in a separate protected workflow described in Section 11.

### 4.3 End-to-end tests

Standard E2E uses XCUITest and launches the real application bundle built for testing.

Required properties:

- deterministic startup state;
- stable accessibility identifiers for controls used by tests;
- isolated temporary user data;
- no production credentials;
- no dependency on release signing secrets;
- critical user flows rather than exhaustive UI traversal.

Application repositories should expose a test-mode contract such as launch arguments or environment variables that can:

- select a temporary data directory;
- disable animations when possible;
- inject deterministic fixtures;
- disable or fake network access;
- seed deterministic time/random values;
- select explicit Light/Dark appearance when the app supports it.

### 4.4 Visual regression

Visual regression consumes PNG files produced by one or more adapters and compares them with the configured baseline source.

The core CI contract is therefore:

```text
capture adapter
      |
      v
artifacts/visual/current/<case-id>.png
      |
      v
baseline resolver
      |
      +-- Git baseline
      `-- rolling main artifact baseline
      |
      v
visual comparator
      |
      +-- expected.png
      +-- actual.png
      +-- diff.png
      `-- report.json
```

The comparator does not care whether the PNG came from XCUITest, a component snapshot test, SwiftUI rendering, or another mechanism.

## 5. Workflow architecture

Planned workflow structure:

```text
.github/workflows/
  tests.yml
  visual-regression.yml
  reusable-swift-tests.yml
  reusable-macos-e2e.yml
  reusable-visual-regression.yml
```

Existing quality and release workflows remain separate.

### 5.1 `tests.yml`

Repository-level caller for normal PR and `main` validation.

Responsibilities:

- invoke unit/integration tests;
- collect coverage;
- apply the coverage ratchet when a baseline exists;
- expose stable status-check names for Rulesets.

### 5.2 `reusable-swift-tests.yml`

Reusable unit/integration test engine.

Initial adapter model:

- `xcode`
- `swiftpm`

Xcode inputs should cover:

- workspace or project path;
- scheme;
- optional test plan;
- explicit destination;
- optional DerivedData path;
- coverage enable/disable;
- test category selection where the project supports separate plans/targets.

SwiftPM inputs should remain minimal and use `swift test` with coverage when enabled.

The first implementation should prefer structured inputs over an arbitrary shell command. If an application needs custom setup, that setup belongs in the caller's secret-free workflow before invoking the reusable test workflow or in a narrowly defined adapter extension.

### 5.3 `reusable-macos-e2e.yml`

Runs XCUITest on a pinned macOS environment.

Responsibilities:

- build-for-testing/test-without-building or equivalent deterministic Xcode flow;
- execute the selected UI test plan/target;
- collect `.xcresult`;
- export logs and screenshots required for visual comparison;
- upload diagnostics on failure;
- avoid Apple release credentials entirely.

### 5.4 `visual-regression.yml`

Repository-level caller for visual checks.

Triggers:

- pull requests affecting application/UI/test/visual configuration;
- pushes to `main` so new rolling baselines can be published after a successful run;
- manual dispatch for baseline investigation.

### 5.5 `reusable-visual-regression.yml`

Responsibilities:

1. validate the visual manifest;
2. retrieve Git-backed expected images;
3. resolve the latest trusted rolling baseline from successful `main` runs;
4. verify baseline metadata/profile compatibility;
5. compare images;
6. write a human-readable job summary;
7. upload visual reports/artifacts;
8. publish a new rolling baseline only on a successful trusted `main` run.

The workflow must not automatically modify Git-backed baselines.

## 6. Canonical visual environment

Pixel comparisons require a stable execution profile.

The visual workflow must not use mutable `macos-latest` as the canonical baseline runner. The initial template profile uses the explicit GA runner label:

```text
macos-26
```

The repository must also pin or explicitly select an Xcode installation for visual tests. Updating the canonical macOS or Xcode version is a policy/baseline change and should be reviewed through an ordinary PR.

Canonical profile metadata must include at least:

- runner OS label/version;
- CPU architecture;
- Xcode version/path;
- display scale when relevant;
- locale;
- language;
- appearance (Light/Dark);
- application test configuration identifier.

Two images from incompatible canonical profiles must not be silently compared. The workflow should fail with a profile-mismatch diagnostic or require an explicit baseline migration.

## 7. Visual baseline model

### 7.1 Tier A: Git baseline

Use for stable, critical UI that should be reviewed directly in source control.

Recommended path:

```text
Tests/VisualBaselines/<profile>/<case-id>.png
```

Good candidates:

- main window states;
- settings/preferences;
- onboarding steps;
- error/empty states;
- critical confirmation dialogs;
- stable menu/popover states.

Rules:

- baseline updates are committed explicitly;
- CI never auto-records and pushes Git baselines;
- changed baseline PNGs appear in the same PR as the intentional UI change;
- CODEOWNERS may protect the baseline directory in Team mode.

### 7.2 Tier B: rolling `main` artifact baseline

Use for large, dynamic, numerous, or environment-sensitive visual captures where permanently committing every image would create repository noise.

Baseline source requirements:

- repository: current repository only;
- branch: `main` only;
- workflow: expected visual workflow only;
- conclusion: successful run only;
- artifact: expected canonical artifact name only;
- profile metadata: must match the current canonical visual profile.

A PR artifact must never become another PR's baseline.

On successful `main` execution, the visual workflow publishes the current rolling set as the new baseline artifact.

### 7.3 Bootstrap behavior

The first rolling baseline does not exist until the feature is merged and a successful `main` visual run completes.

The implementation must support an explicit bootstrap state. Missing rolling baseline data may be non-blocking only when the repository configuration deliberately enables bootstrap mode. Once the first trusted baseline exists, the repository should disable bootstrap mode and treat a missing baseline as an error.

## 8. Visual manifest

Use a dependency-free machine-readable manifest. The initial design uses JSON rather than YAML so the comparator/validator can parse it without adding a YAML runtime dependency.

Proposed location:

```text
Tests/VisualRegression/visual-regression.json
```

Conceptual schema:

```json
{
  "schemaVersion": 1,
  "profile": "macos-26-arm64-xcode-pinned",
  "cases": [
    {
      "id": "settings-light",
      "baseline": "git",
      "current": "artifacts/visual/current/settings-light.png",
      "expected": "Tests/VisualBaselines/macos-26-arm64-xcode-pinned/settings-light.png",
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

Thresholds are explicit policy rather than hidden comparator defaults.

Dimension mismatch always fails.

A case may use strict equality or a documented tolerance. Raising a tolerance is a reviewable policy change and must not be used to hide an unexplained regression.

## 9. Visual comparator

The core comparator should be a repository-owned small tool rather than an opaque hosted service or mandatory third-party snapshot dependency.

Preferred first implementation: a Swift command-line tool using macOS-native image frameworks so no additional runtime package manager is required on the canonical runner.

Responsibilities:

- decode PNG images;
- normalize to a deterministic pixel format/color space;
- reject incompatible dimensions;
- calculate per-pixel channel deltas;
- count changed pixels;
- calculate changed-pixel ratio;
- calculate maximum channel delta;
- generate a visual diff PNG;
- emit machine-readable JSON;
- return non-zero when configured thresholds are exceeded.

Required report fields:

```text
case id
baseline source
baseline SHA/run id where applicable
current commit SHA
profile id
expected dimensions
actual dimensions
changed pixel count
changed pixel ratio
max channel delta
pass/fail
```

Third-party libraries such as SnapshotTesting remain optional capture adapters. They are not the source of truth for the CI comparison contract.

## 10. PR review experience

Visual CI must provide useful output without granting `pull-requests: write` to ordinary PR jobs.

Use:

- `$GITHUB_STEP_SUMMARY` for the textual comparison summary;
- GitHub Actions artifacts for image inspection;
- stable check names for branch Rulesets.

For each failed visual case, the artifact layout should contain:

```text
visual-report/
  <case-id>/
    expected.png
    actual.png
    diff.png
    report.json
```

The PR report artifact should be uploaded even when the visual gate passes when doing so remains within practical storage limits, because reviewers may want to inspect an intentional change before updating a Git baseline.

Recommended retention policy:

- PR visual reports: 14 days;
- failed E2E `.xcresult` and diagnostics: 14 days;
- rolling `main` visual baseline: maximum practical repository retention, targeted at 90 days where supported.

A missing rolling baseline caused by retention expiry should produce a clear failure rather than silently accepting the current images.

## 11. Privileged system E2E

Some macOS applications interact with APIs that require Accessibility, Screen Recording, Automation, input monitoring, system extensions, or other TCC-controlled permissions.

These tests must not make normal fork/PR CI privileged.

Define two E2E profiles:

### Standard E2E

- GitHub-hosted macOS runner;
- secret-free;
- no privileged TCC assumptions;
- runs on PR and `main`;
- required status check for critical flows that fit this environment.

### Privileged system E2E

- optional dedicated self-hosted or specially prepared runner;
- `main`, scheduled, or manual triggers only;
- protected test environment if test credentials are required;
- never uses release signing/notarization secrets;
- isolated test credentials distinct from production/release credentials;
- not triggered by arbitrary fork PR code.

Apps such as window managers, screen overlays, capture utilities, or deep system integrations can keep their normal application logic covered by Standard E2E while moving permission-sensitive scenarios to Privileged system E2E.

## 12. Coverage ratchet

Coverage is a regression signal, not a vanity target.

For Xcode projects, collect coverage from `.xcresult` using native Xcode tooling. For SwiftPM, use Swift's coverage support.

Generate a normalized summary artifact such as:

```text
coverage-summary.json
```

The summary should contain project and target-level coverage values where available.

PR policy:

- compare against the latest successful trusted `main` coverage baseline;
- fail on an unexplained regression beyond a configurable tolerance;
- do not require an arbitrary global 80% threshold for an existing application;
- new projects may start with a stricter minimum and zero-regression policy.

Initial template default should allow a small configurable floating-point/tooling tolerance while treating substantive decreases as blocking.

Coverage baseline artifacts follow the same trust rule as visual rolling baselines: successful `main` only.

## 13. Flakiness policy

A retry must not silently convert a flaky required test into a green signal.

Default policy:

- unit tests: no automatic retry;
- integration tests: no automatic retry;
- required E2E: no automatic retry in the blocking job;
- visual comparison: no retry after a deterministic capture failure except infrastructure-level job reruns initiated explicitly.

Optional scheduled stability jobs may repeat critical E2E scenarios multiple times to measure flakiness. Those results should be reported separately from the required PR gate.

A flaky test should be fixed or quarantined with a documented issue and narrow scope. Blanket retry settings are not an acceptable long-term policy.

## 14. Accessibility and testability conventions

Coding standards should require stable accessibility identifiers for controls used by E2E tests.

Rules:

- identifiers are stable API for tests and should not depend on user-visible localized strings;
- tests prefer accessibility identifiers over coordinates or fragile view hierarchy traversal;
- test-only behavior must be explicit and must not weaken production security;
- deterministic fixture injection should occur through narrow app adapters/launch configuration rather than global mutable state where practical.

## 15. CI trigger and cost policy

### Pull requests

Required by default:

- unit tests;
- integration tests when configured;
- Standard E2E for critical flows;
- Git baseline visual cases;
- rolling-baseline visual cases once bootstrapped;
- coverage ratchet.

Use concurrency cancellation for superseded commits on the same PR.

### `main`

Run the same required suite and, only after successful comparison/tests:

- publish the new rolling visual baseline;
- publish the new coverage baseline.

### Scheduled/manual

Use for:

- expanded OS/Xcode matrix;
- repeated flake detection;
- Privileged system E2E;
- longer-running compatibility checks.

Avoid multiplying expensive macOS runner minutes across every PR unless the extra matrix dimension has demonstrated value.

## 16. Security model

Test jobs follow the existing least-privilege model.

PR jobs:

- `contents: read` by default;
- `actions: read` only where trusted `main` artifacts must be resolved;
- no Apple Developer ID secrets;
- no App Store Connect notarization secret;
- no production credentials;
- no `pull_request_target` checkout/execution pattern.

Rolling baselines must be downloaded only from trusted successful `main` workflow runs.

Privileged system E2E credentials, if ever required, live in a separate protected test Environment. They must never share the `release` Environment.

## 17. Failure modes and expected behavior

### Missing Git baseline

Fail the visual case with an explicit missing-baseline diagnostic.

### Missing rolling baseline

- bootstrap enabled: mark as bootstrap/non-comparable and do not publish a false comparison result;
- bootstrap disabled: fail.

### Profile mismatch

Fail before pixel comparison and show expected/current profile metadata.

### Dimension mismatch

Fail and include both dimensions in `report.json`.

### Capture missing

Fail the case and preserve the E2E/xcresult diagnostics.

### XCUITest failure before screenshot

E2E gate fails. Visual gate must not claim the UI matched.

### Artifact lookup failure

Fail explicitly after bounded retries for GitHub API/infrastructure errors; do not substitute a PR artifact or silently seed a baseline.

### Changed UI is intentional

- Git baseline case: developer records/reviews the new baseline PNG in the PR;
- rolling case: PR shows the visual diff; after merge and successful `main`, the trusted rolling baseline advances automatically.

## 18. Planned repository additions

```text
.github/workflows/
  tests.yml
  visual-regression.yml
  reusable-swift-tests.yml
  reusable-macos-e2e.yml
  reusable-visual-regression.yml

scripts/
  test/
    export-coverage.sh
    compare-coverage.sh
  visual/
    validate-manifest.sh
    collect-metadata.sh

Tools/
  VisualDiff/
    Package.swift
    Sources/VisualDiff/...
    Tests/VisualDiffTests/...

Tests/
  VisualRegression/
    visual-regression.example.json
  VisualBaselines/
    .gitkeep

docs/
  TESTING.md
  VISUAL_REGRESSION.md
```

Exact casing may be normalized to match the repository's final conventions during the implementation plan, but responsibilities should remain separated.

## 19. Test strategy for the template itself

The template repository currently has no real application UI, so the new infrastructure must be testable without pretending to run an app that does not exist.

Template self-tests should include:

- manifest validation fixtures;
- PNG comparator unit tests with identical images;
- single-pixel change fixture;
- tolerated-delta fixture;
- dimension mismatch fixture;
- invalid/missing baseline fixture;
- coverage summary comparison fixtures;
- workflow syntax/security validation through existing actionlint/zizmor;
- shell formatting/linting through existing shfmt/ShellCheck.

The template may generate tiny deterministic test PNG fixtures programmatically or keep minimal fixtures where binary repository content is justified.

Real XCUITest/E2E validation must happen in an adopter application repository such as SchneeBar or SchneeGlass after the generic workflow contract is implemented.

## 20. Ruleset integration

Once the workflows exist and have produced stable check names, the recommended `main` Ruleset should require:

- existing quality/security checks;
- unit/integration test check;
- Standard E2E check when the app configures it;
- visual-regression check when the app configures it;
- coverage regression check when enabled.

Do not configure a required check before the corresponding workflow can run on all relevant PRs; otherwise a path-filtered workflow can leave the PR permanently waiting.

## 21. Rollout plan

### Phase A — core deterministic comparison

- visual manifest schema;
- VisualDiff tool and unit tests;
- Git baseline comparison;
- report artifact generation.

### Phase B — generic unit/integration workflow

- Xcode and SwiftPM adapters;
- `.xcresult`/coverage export;
- coverage ratchet fixtures.

### Phase C — macOS E2E

- reusable XCUITest workflow;
- diagnostics and `.xcresult` artifacts;
- screenshot output contract.

### Phase D — rolling `main` baseline

- trusted successful-main artifact lookup;
- metadata/profile validation;
- baseline publication after successful `main` visual run;
- bootstrap handling.

### Phase E — adopter validation

Apply the template to one real macOS app and verify:

1. unit/integration CI;
2. XCUITest critical flow;
3. Git visual baseline comparison;
4. rolling visual baseline comparison;
5. intentional baseline-update flow;
6. failing UI diff artifact;
7. coverage regression behavior.

## 22. Acceptance criteria

The design is implemented successfully when:

- a macOS app can enable unit/integration tests with minimal caller configuration;
- a macOS app can run secret-free XCUITest in PR CI;
- screenshots from any compliant adapter can be compared without coupling CI to that adapter;
- both Git and rolling-main baseline sources can be used in one manifest;
- visual failures provide expected/actual/diff PNGs and machine-readable metrics;
- rolling baselines can only originate from successful trusted `main` runs;
- baseline profile mismatch is detected before comparison;
- coverage cannot regress beyond configured policy without CI failure;
- test jobs never gain release credentials;
- permission-sensitive macOS E2E can be isolated from ordinary fork PR CI;
- the template's own comparator/config/coverage logic has deterministic automated tests;
- existing quality/action-security checks remain green.
