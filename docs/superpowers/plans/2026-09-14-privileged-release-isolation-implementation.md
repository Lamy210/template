# Privileged Release Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate version-tag application builds from privileged macOS signing/publication so tag-selected code never receives Apple credentials or repository write permission.

**Architecture:** A tag-triggered `Release Build` workflow remains secret-free and uploads an unsigned `.app` tar plus deterministic provenance. A default-branch `workflow_run` publisher performs secret-free GitHub/provenance/artifact validation first, re-handoffs the validated tar inside the publisher run, and only then invokes privileged signing/publication code from the publisher/default-branch commit.

**Tech Stack:** GitHub Actions, Bash, Python 3 standard library, GitHub CLI/REST API, existing macOS release scripts.

**Spec:** `docs/superpowers/specs/2026-09-14-privileged-release-isolation-design.md`

## Global Constraints

- Tag-build workflow has no Apple credentials, no release Environment, and no repository write permission.
- Privileged publisher control code is selected by the current default-branch workflow, never by the tag commit.
- Validation job and signing job remain separate jobs.
- Unknown provenance fields are rejected for schema version 1.
- Publisher validates repository/workflow identity, event, run ID/attempt, source SHA, tag/ref, artifact identity, and digests before privileged work.
- The signing job executes scripts only from the trusted publisher/default-branch checkout.
- Preserve PR #3 archive confinement, executable checks, immutable/idempotent GitHub Release publication, and DMG verification.
- Python implementation uses only the standard library.
- No `pull_request_target`, permanent bypass actor, or Administration credential is introduced.

---

### Task 1: Build provenance schema and validator

**Files:**
- Create: `scripts/release/release_provenance.py`
- Create: `scripts/release/test_release_provenance.py`
- Create: `scripts/release/write-build-provenance.py`

**Interfaces:**
- Produces `validate_build_provenance(document: object, expected: ExpectedBuild) -> list[str]`.
- Produces CLI writer inputs for repository, workflow path/name, run ID/attempt, SHA/ref/tag, artifact/archive identity, app basename, bundle ID, and version.
- Later tasks rely on deterministic schema-v1 JSON and exact `sha256:<64 lowercase hex>` validation.

- [ ] **Step 1: Write failing unit tests** covering valid schema, unknown/missing fields, bool-vs-int confusion, malformed SHA/digest, malformed tag/ref/version, wrong workflow path, wrong run ID/attempt, unsafe app/archive basenames, and cross-field tag/version/ref mismatch.
- [ ] **Step 2: Run `python3 -m unittest scripts.release.test_release_provenance -v` and verify RED because the module is absent.**
- [ ] **Step 3: Implement the minimal strict schema validator** using dataclasses/stdlib only. Exact schema-v1 keys are those in the design spec; no extras are accepted.
- [ ] **Step 4: Implement `write-build-provenance.py`** so the unprivileged workflow can write canonical sorted JSON and compute the tar SHA-256 itself rather than trusting caller text.
- [ ] **Step 5: Re-run unit tests and CLI smoke fixtures; require GREEN.**
- [ ] **Step 6: Commit `feat: add strict release build provenance`.**

### Task 2: Exact triggering-run and artifact resolver

**Files:**
- Create: `scripts/release/resolve-release-build-artifact.sh`
- Create: `scripts/release/test-resolve-release-build-artifact.sh`
- Create: `scripts/release/validate-actions-artifact.py`
- Create: `scripts/release/test_validate_actions_artifact.py`

**Interfaces:**
- Consumes triggering run ID/attempt, current repository, canonical workflow path, expected artifact name, and output directory.
- Produces a fresh directory containing only `unsigned-macos-app.tar.gz`, `build-provenance.json`, and resolver-generated `source-artifact-metadata.json`.
- Exit codes distinguish policy rejection from API/transport failure.

- [ ] **Step 1: Add RED fixtures** for wrong repository, fork head repository, wrong workflow ID/path, non-push event, unsuccessful run, mismatched attempt, expired artifact, ambiguous exact-name artifacts, unsafe ZIP traversal/absolute paths/symlinks/duplicates, and malformed GitHub digest.
- [ ] **Step 2: Verify RED against missing resolver/validator.**
- [ ] **Step 3: Implement resolver with bounded `gh api` calls** that re-fetches the exact run and canonical workflow identity rather than trusting only `workflow_run` event text.
- [ ] **Step 4: Validate the Actions Artifact ZIP before extraction** using Python stdlib; reject absolute paths, drive prefixes, `..`, duplicate canonical paths, symlinks and unexpected top-level files.
- [ ] **Step 5: Require exactly one non-expired artifact named `unsigned-macos-release-<run-id>-<attempt>` and record GitHub artifact ID/digest.**
- [ ] **Step 6: Run shell/Python suites to GREEN and commit `feat: resolve exact release build artifact`.**

### Task 3: Publisher-side provenance, tag and app preflight

**Files:**
- Create: `scripts/release/validate-release-input.py`
- Create: `scripts/release/test_validate_release_input.py`
- Modify: `scripts/release/extract-app-artifact.sh`
- Reuse: `scripts/release/verify-app-executable.sh`

**Interfaces:**
- Consumes independently fetched run/artifact metadata, strict build provenance, repository tag resolution, publisher configuration, and downloaded tar.
- Produces `validated-release-metadata.json` plus the unchanged validated tar.

- [ ] **Step 1: Add RED tests** for provenance self-consistency that disagrees with GitHub metadata, tag not resolving to head SHA, annotated-tag dereference mismatch, source commit not reachable from default branch, archive digest mismatch, bundle ID/version/executable mismatch, and publisher config mismatch.
- [ ] **Step 2: Verify RED before implementation.**
- [ ] **Step 3: Implement strict cross-checks**; provenance is a claim, never an authority. Require tag `^v[0-9]+\.[0-9]+\.[0-9]+$`, exact `refs/tags/<tag>`, exact version, and exact 40-char lowercase SHA.
- [ ] **Step 4: Run PR #3 tar preflight before privileged work** and parse `Info.plist` in this secret-free validation phase to verify bundle ID, short version, executable name and executable contract.
- [ ] **Step 5: Generate validator-owned metadata** containing source run/attempt/SHA/tag/artifact ID/digest/archive digest/publisher SHA.
- [ ] **Step 6: Run all tests GREEN and commit `feat: validate release input before secrets`.**

### Task 4: Secret-free tag build workflow

**Files:**
- Create: `examples/app-release-build.yml`
- Modify: `examples/app-release.yml` (replace monolithic example with migration note or split entry point)
- Modify: `docs/RELEASE.md`

**Interfaces:**
- Emits one artifact named `unsigned-macos-release-${{ github.run_id }}-${{ github.run_attempt }}` containing exactly `release-input/unsigned-macos-app.tar.gz` and `release-input/build-provenance.json`.

- [ ] **Step 1: Add workflow contract checks** to Quality that assert workflow-level `permissions: {}`, build-job `contents: read`, no Environment, no write permission, no Apple/Homebrew secrets, unique artifact naming, and provenance writer invocation.
- [ ] **Step 2: Verify contract test RED against current monolithic example.**
- [ ] **Step 3: Add `Release Build` example** using existing package helper plus the provenance writer.
- [ ] **Step 4: Run actionlint/zizmor/contract tests GREEN.**
- [ ] **Step 5: Commit `feat: add secret-free release build workflow`.**

### Task 5: Default-branch workflow_run publisher validation

**Files:**
- Create: `.github/workflows/reusable-release-publisher.yml` or `examples/app-release-publisher.yml` as appropriate for the generated-template model; the publisher workflow itself must be a top-level `workflow_run` workflow in adopters.
- Modify: `.github/workflows/quality.yml`
- Modify: `docs/RELEASE.md`

**Interfaces:**
- Trigger: `workflow_run` completed for canonical `Release Build` workflow.
- Validation job permissions: `actions: read`, `contents: read`, no Environment.
- Validation job uploads `validated-release-input-<source-run-id>-<attempt>` for the current publisher run.

- [ ] **Step 1: Add RED workflow contract tests** proving the publisher file uses `workflow_run`, has workflow-level `permissions: {}`, keeps validation secret-free/no Environment, and gates privileged work on validation success.
- [ ] **Step 2: Implement publisher validation job** that invokes Tasks 2 and 3 and re-uploads the unchanged validated tar plus validator-owned metadata.
- [ ] **Step 3: Ensure concurrency groups by source build run ID and `cancel-in-progress: false`.**
- [ ] **Step 4: Run actionlint/zizmor/contract tests GREEN.**
- [ ] **Step 5: Commit `feat: add default-branch release publisher validation`.**

### Task 6: Migrate privileged signing/publication to trusted publisher inputs

**Files:**
- Modify: `.github/workflows/reusable-macos-release.yml`
- Modify: publisher workflow/example from Task 5
- Modify: `scripts/release/verify-release.sh` only if needed for explicit expected tag/version inputs
- Modify: `docs/RELEASE.md`

**Interfaces:**
- Privileged reusable workflow no longer derives release tag/version from `github.ref_name`.
- It consumes validated `source_tag`, `source_sha`, `validated_artifact_name`, archive digest, app basename, bundle ID, and version from the publisher validation result.

- [ ] **Step 1: Add RED contract tests** showing `github.ref_name`/tag-selected checkout cannot control privileged release semantics and that the signing job attaches `environment: release` only after validation.
- [ ] **Step 2: Refactor privileged workflow inputs** to explicit validated source tag/version/SHA and same-run validated artifact name.
- [ ] **Step 3: Checkout publisher `github.sha` for scripts/entitlements**; never checkout release tag into the control-code directory.
- [ ] **Step 4: Before certificate import, recompute archive digest, rerun tar preflight, and reverify bundle ID/version/executable.**
- [ ] **Step 5: Preserve signing, DMG, notarization, mounted-payload verification, immutable GitHub Release publication, and Homebrew-after-publication ordering.**
- [ ] **Step 6: Run release regression suites/actionlint/zizmor GREEN and commit `fix: isolate privileged release control code`.**

### Task 7: Adversarial integration and operator documentation

**Files:**
- Create: `scripts/release/test-release-isolation-contract.sh`
- Modify: `.github/workflows/quality.yml`
- Modify: `docs/RELEASE.md`
- Modify: issue/PR documentation as needed.

**Interfaces:**
- Static/integration fixtures prove old ancestor tags cannot select privileged control code and malformed/untrusted artifacts fail before the release Environment boundary.

- [ ] **Step 1: Add adversarial fixtures** for old trusted ancestor tag, wrong run attempt, wrong workflow ID/path, fork repository, tag-to-SHA mismatch, expired/ambiguous artifact, tampered provenance, tampered archive after provenance, and publisher artifact digest mismatch.
- [ ] **Step 2: Assert no tag-build workflow/job has `contents: write`, Environment, Apple secret references or Homebrew token references.**
- [ ] **Step 3: Assert only the privileged signing/publication job attaches `environment: release`.**
- [ ] **Step 4: Run all Python, shell, actionlint, ShellCheck, shfmt, zizmor and Swift Quality checks.**
- [ ] **Step 5: Update `docs/RELEASE.md` with rollout, retry, artifact expiry, immutable tag, and recovery procedures.**
- [ ] **Step 6: Commit `test: verify privileged release isolation`.**

### Task 8: Final review and branch completion

**Files:**
- No new production files unless review finds a defect.

- [ ] **Step 1: Re-review the complete diff against every security objective and non-goal in the spec.**
- [ ] **Step 2: Run fresh latest-head CI and record exact run IDs/head SHA.**
- [ ] **Step 3: Confirm PR #3 archive hardening and immutable publication regressions still pass.**
- [ ] **Step 4: Confirm PR #4 governance work remains independent; do not merge Ruleset administration into this release architecture PR.**
- [ ] **Step 5: Request code review and resolve all blocking findings before marking ready.**
