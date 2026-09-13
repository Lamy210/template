# Regression Infrastructure Hardening Design

Date: 2026-09-13
Status: Draft for review

## 1. Purpose

Harden the test, E2E, coverage, and visual-regression foundation so that it remains safe and deterministic across long-lived repositories, fork pull requests, GitHub-hosted runner changes, intentional UI redesigns, artifact retention expiry, and future adopter applications such as SchneeBar or SchneeGlass.

This document extends `2026-09-13-test-e2e-visual-regression-design.md`. Where the two documents differ, this hardening design takes precedence for the affected areas.

## 2. Design principles

The regression platform must distinguish four different questions:

1. Did the application behave correctly?
2. Did the UI change?
3. If the UI changed, was that exact change explicitly approved?
4. Is the baseline itself trusted and compatible with the current execution profile?

A passing comparison is not enough when the baseline is untrusted, stale, profile-incompatible, or implicitly replaced.

The platform therefore treats baseline provenance, profile identity, approval identity, and test output identity as first-class data.

## 3. Final regression result states

Visual cases use explicit states rather than a binary pass/fail model:

- `passed`: current capture matches the trusted baseline within the declared policy.
- `failed`: the capture differs and no valid approval exists, or comparison cannot be performed safely.
- `approved-change`: the current capture differs, but an exact, reviewable approval record matches the old baseline digest, new image digest, case ID, and controlled profile fingerprint.
- `bootstrap`: the case is genuinely new and has no trusted rolling baseline yet.

`approved-change` is a successful policy outcome but must remain visibly distinct from `passed` in reports.

`bootstrap` is not equivalent to `passed` and is allowed only for cases that are demonstrably new according to the previous trusted baseline bundle manifest.

## 4. Intentional visual change approval protocol

### 4.1 Problem

A rolling baseline normally advances after a successful `main` run. Without an approval mechanism, an intentional UI redesign would fail the PR visual gate and therefore could never merge to create the new `main` baseline.

### 4.2 Approval records

Intentional visual changes are approved through source-controlled records under:

```text
Tests/VisualRegression/Approvals/<case-id>.json
```

Conceptual schema:

```json
{
  "schemaVersion": 1,
  "caseId": "settings-light",
  "fromDigest": "sha256:...",
  "toDigest": "sha256:...",
  "profileFingerprint": "sha256:...",
  "reason": "Redesigned settings sidebar"
}
```

Required fields:

- schema version;
- exact case ID;
- exact trusted baseline image SHA-256 digest;
- exact current capture SHA-256 digest;
- exact controlled profile fingerprint;
- non-empty human reason.

### 4.3 Approval validation

An approval is valid only when all identity fields match the comparison being reviewed.

A record must not authorize:

- a later unrelated UI change;
- a different baseline revision;
- a different capture;
- a different profile;
- a different case.

Therefore old approval records cannot silently become blanket suppressions.

When the current image digest changes, the approval stops matching and the visual gate returns to `failed` until a new exact approval is reviewed.

### 4.4 Git baseline behavior

For Git baselines, the preferred approval mechanism remains updating the baseline PNG in the same PR. Approval records are primarily required to solve the rolling-baseline merge deadlock.

A repository may still use approval records for Git baselines when it wants an explicit audit trail, but this is optional in the first implementation.

### 4.5 CODEOWNERS integration

Team-mode repositories should be able to protect:

```text
Tests/VisualRegression/Approvals/**
Tests/VisualBaselines/**
```

with CODEOWNERS.

The template must document this as an optional governance layer, not require it for solo repositories.

## 5. Trusted baseline artifact provenance

### 5.1 Trust requirements

A rolling baseline or coverage baseline is trusted only when it originates from the current repository and satisfies all of the following:

- expected repository identity;
- expected workflow identity/path;
- `event == push`;
- `head_branch == main`;
- `conclusion == success`;
- expected artifact name;
- artifact is not expired;
- run attempt metadata is recorded;
- source commit SHA is recorded;
- artifact ID and GitHub-provided artifact digest are recorded when available.

A pull-request run must never become a rolling baseline source.

A manually uploaded file or artifact from another repository must never be silently substituted.

### 5.2 Bundle structure

Rolling baseline artifacts use a self-describing bundle:

```text
visual-baseline/
  bundle-manifest.json
  profile.json
  images/
    <case-id>.png
```

Coverage baselines use an analogous structure with `coverage-summary.json`.

### 5.3 Bundle manifest

The bundle manifest records at least:

- schema version;
- repository identity;
- workflow identity;
- source run ID;
- run attempt;
- source commit SHA;
- creation timestamp;
- controlled profile fingerprint;
- previous trusted baseline reference when applicable;
- case IDs included in the bundle;
- SHA-256 digest for each image;
- artifact digest when exposed by GitHub.

The resolver validates both the GitHub artifact provenance and the file-level digests inside the bundle.

### 5.4 Archive extraction safety

Artifact ZIP extraction must reject:

- absolute paths;
- `..` traversal;
- symlinks escaping the extraction root;
- duplicate canonical paths;
- unexpected files when strict bundle mode is enabled.

The resolver extracts into a fresh temporary directory and only exposes validated files to later comparison steps.

## 6. Controlled profile fingerprint

### 6.1 Two metadata layers

Visual compatibility is divided into `ControlledProfile` and `ObservedRuntime`.

`ControlledProfile` contains values the repository deliberately controls and that materially define comparable rendering:

- canonical macOS runner family;
- CPU architecture;
- Xcode/toolchain version policy;
- locale;
- language;
- timezone;
- appearance;
- display scale and capture geometry when relevant;
- application fixture/test configuration version;
- capture contract version;
- visual comparator schema version.

`ObservedRuntime` records diagnostic values that may drift without automatically invalidating every baseline:

- exact macOS build;
- exact GitHub runner image version;
- exact Xcode build identifier;
- runner host metadata appropriate for diagnostics.

### 6.2 Fingerprint

`ControlledProfile` is encoded as canonical JSON and SHA-256 hashed:

```text
profileFingerprint = SHA256(canonical ControlledProfile JSON)
```

Pixel comparison is forbidden when controlled profile fingerprints differ.

Observed runtime differences appear in diagnostics and may trigger warnings or scheduled drift checks, but they do not automatically force a baseline migration unless they demonstrably affect rendering.

### 6.3 Profile migration

A controlled profile change is a reviewed baseline migration.

The PR must make the policy change explicit and either:

- update Git baselines;
- approve intended rolling baseline transitions;
- enter an explicit migration/bootstrap flow when the old and new profiles are intentionally incomparable.

## 7. Case-level bootstrap semantics

Global bootstrap flags are too broad once a repository has established baselines.

The previous trusted rolling bundle contains the prior case index.

Given:

```text
previous: A B C
current:  A B C D
```

then:

- missing baseline for A/B/C is an error;
- missing baseline for D may be `bootstrap` because D is demonstrably new.

A newly added case becomes part of the next successful trusted `main` baseline publication.

Repository-wide bootstrap is allowed only before the first trusted baseline exists at all, or during an explicit controlled-profile migration.

## 8. Baseline retention and refresh

GitHub Actions artifacts are not a permanent datastore. The architecture must not assume a rolling baseline survives indefinitely without repository activity.

The template supports a scheduled baseline refresh workflow that:

1. runs against current trusted `main`;
2. captures the current visual set;
3. resolves the previous trusted baseline;
4. compares before publication;
5. publishes a replacement rolling baseline only if policy succeeds.

This refresh also acts as a rendering-drift detector for runner-image and host changes.

The refresh must not silently accept a mismatch just to extend retention.

If the old trusted baseline is already unavailable and the repository is not in an explicit migration/bootstrap state, the scheduled job fails and asks for deliberate recovery.

## 9. Coverage baseline hardening

### 9.1 Raw counts, not only percentages

`coverage-summary.json` stores both ratios and raw counts.

Conceptual schema:

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

Target-level summaries should be included when the underlying tool provides reliable target boundaries.

### 9.2 Coverage profile

The coverage profile records policy inputs such as:

- included targets;
- excluded targets;
- generated-source exclusions;
- test-source exclusions;
- toolchain identity relevant to coverage extraction;
- coverage schema version.

A coverage profile change is not treated as an ordinary coverage regression.

It requires a baseline migration or explicit policy update because the denominator may have changed.

### 9.3 Ratchet policy

PR evaluation distinguishes:

- genuine coverage decrease under the same profile;
- denominator/profile change;
- missing trusted baseline;
- allowed numeric tooling tolerance.

The template does not impose a universal 80% target on existing applications.

## 10. Required Gate aggregation

### 10.1 Problem

Making every internal job a separate repository Ruleset requirement creates brittle configuration, especially when optional features or path-sensitive jobs are skipped.

### 10.2 Stable external check

The template exposes one stable blocking check:

```text
Tests / Required Gate
```

Internal checks remain visible for diagnosis:

- Unit;
- Integration;
- E2E;
- Visual;
- Coverage.

The aggregator runs with `if: always()` and evaluates the required/optional status of each configured subsystem.

### 10.3 Not-applicable semantics

A subsystem may report:

- success;
- failure;
- not-applicable;
- disabled by repository configuration.

`not-applicable` must not be indistinguishable from a workflow that never started.

Required workflow files therefore should not rely on top-level `paths:` filters that can leave a Ruleset check permanently pending.

Instead, a lightweight change classifier may decide which internal jobs are applicable while the Required Gate itself always exists.

### 10.4 Required Gate failure rules

The Required Gate fails when any configured required subsystem:

- fails;
- is cancelled unexpectedly;
- never produces a valid result;
- encounters an unsafe baseline/profile/provenance state.

Optional scheduled compatibility jobs do not block this gate unless the adopting repository explicitly promotes them to required status.

## 11. Fork pull request model

Public fork PRs are treated as untrusted code.

Default PR test jobs remain secret-free and must not use `pull_request_target` to execute fork code with elevated permissions.

When a PR needs access to trusted baseline metadata, the workflow may receive only the minimum read permissions necessary to resolve artifacts from already-trusted `main` runs.

The baseline lookup path must not execute code downloaded from the baseline artifact; artifacts are treated as data only.

Any future workflow requiring write permissions must be separated from untrusted PR execution.

## 12. E2E determinism contract

Visual and E2E adapters should stabilize more than the OS/Xcode version.

A canonical capture should control, where relevant:

- window size;
- window position or element capture region;
- appearance;
- locale;
- language;
- timezone;
- animation policy;
- test clock;
- random seed;
- fixture dataset;
- network responses;
- selection state;
- focus state;
- scroll position.

### 12.1 Capture scope

Prefer capturing a specific application window or `XCUIElement` instead of the full desktop.

This reduces irrelevant differences from:

- menu-bar time;
- desktop wallpaper;
- notifications;
- unrelated windows;
- cursor position;
- host-level chrome.

### 12.2 Readiness synchronization

Tests must not rely on arbitrary fixed sleeps as the primary readiness mechanism.

Applications should expose deterministic readiness through an accessibility identifier/state or another explicit test contract.

Captures occur after the readiness condition succeeds within a bounded timeout.

## 13. Privileged system E2E isolation

Permission-sensitive tests remain outside normal public PR execution.

A privileged macOS runner should be treated as disposable infrastructure where practical.

Recommended properties:

- ephemeral VM or resettable runner state;
- dedicated test user;
- only test-specific TCC grants;
- no release/notarization credentials;
- no production credentials;
- no persistent repository write key;
- constrained outbound networking when feasible;
- state reset between executions.

Arbitrary public fork code must never be routed directly to a privileged runner.

## 14. Template fixture application

The template should eventually contain a tiny deterministic fixture macOS application so reusable workflows are tested end-to-end inside the template repository itself.

Suggested location:

```text
Fixtures/MacTestApp/
```

The fixture app should stay intentionally small:

- one window;
- stable accessibility identifiers;
- one button/action;
- one deterministic label/state transition;
- deterministic Light/Dark capture states;
- no network;
- no signing secrets;
- no privileged TCC requirement.

It exists only to validate the reusable infrastructure contract:

- build-for-testing;
- test-without-building;
- XCUITest launch;
- readiness synchronization;
- PNG capture;
- visual comparison;
- `.xcresult` collection;
- coverage extraction.

Real adopter validation in SchneeBar or SchneeGlass remains required before calling the overall foundation production-ready.

## 15. Proposed implementation order

The hardened implementation order is:

1. intentional visual-change approval schema and validation;
2. trusted-main artifact resolver with provenance and safe extraction;
3. bundle manifest and file digest validation;
4. controlled-profile fingerprint and observed-runtime metadata split;
5. case-level rolling bootstrap semantics;
6. Required Gate aggregation contract;
7. coverage summary/profile schema and ratchet;
8. rolling baseline scheduled refresh;
9. reusable unit/integration workflows;
10. reusable Standard E2E workflow;
11. reusable visual-regression workflow;
12. template fixture macOS application;
13. adopter validation in one real macOS application;
14. privileged E2E guidance/optional workflow only when an adopter requires it.

This sequence prioritizes trust and data contracts before adding more workflow surface area.

## 16. Additional acceptance criteria

The regression foundation is not complete until all of the following are true in addition to the original design criteria:

- an intentional rolling-baseline UI change can merge only through an exact digest-bound approval or another explicit reviewed migration mechanism;
- an approval cannot authorize a later unrelated image;
- trusted baseline artifacts are selected only from successful `main` push runs of the expected workflow;
- artifact and per-file digest metadata are preserved and validated where available;
- archive extraction cannot escape its temporary root;
- controlled-profile mismatch prevents pixel comparison;
- observed runtime drift is recorded separately from controlled profile identity;
- established rolling cases cannot silently re-enter bootstrap;
- newly added rolling cases can bootstrap without weakening established cases;
- coverage compares raw counts and ratios under a stable coverage profile;
- coverage profile changes are reported as policy migrations rather than ordinary regressions;
- one stable Required Gate can represent the configured blocking test suite to repository Rulesets;
- documentation discourages top-level path filtering for required workflow checks;
- public fork PR code cannot reach privileged runners or release credentials;
- scheduled baseline refresh never overwrites a mismatching baseline merely to extend artifact retention;
- the template has deterministic self-tests for provenance selection, path safety, approvals, profile compatibility, bootstrap rules, coverage ratchet behavior, and Required Gate decisions;
- a fixture application eventually proves the generic Xcode/XCUITest contract end-to-end.

## 17. Scope boundaries

This hardening does not add:

- automatic CI commits to approve visual changes;
- arbitrary PR comments with elevated write permissions;
- a hosted visual testing service;
- a permanent external artifact store in the first implementation;
- public-fork execution on privileged macOS runners;
- automatic tolerance increases;
- automatic baseline acceptance after failed comparisons.

The default posture is explicit review over silent recovery.
