# P0 Foundation Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the executable-permission loss in the unsigned macOS app artifact handoff and establish stable CI checks that can safely be required by the repository Ruleset.

**Architecture:** The secret-free build job must package the `.app` into a permission-preserving tar archive before GitHub Actions Artifact upload. The privileged release workflow downloads only that archive, validates the archive input, extracts into an isolated directory, and verifies the bundle executable before signing. CI adds an actual upload/download artifact round-trip fixture plus an always-running Swift Quality workflow and a stable `Required gate` aggregation job.

**Tech Stack:** GitHub Actions, Bash, POSIX file modes, tar/gzip, macOS bundle `Info.plist`, SwiftFormat/SwiftLint reusable workflow.

**Spec:** `docs/RELEASE.md`, `docs/BRANCHING.md`, and the 2026-09-13 repository review findings supplied for this remediation.

## Global Constraints

- `main` remains the only long-lived development branch.
- Release credentials remain isolated from secret-free build/test jobs.
- Third-party GitHub Actions remain pinned to full commit SHAs.
- The privileged release job must not execute arbitrary build hooks from the application artifact.
- Release verification must fail when `CFBundleExecutable` is missing or not executable.
- Required checks must not depend on workflow-level `paths:` filters that can leave a required context pending.
- No repository Ruleset mutation is assumed from code; the PR must document the exact settings required after the stable check names have run once.

---

### Task 1: Permission-preserving unsigned app handoff

**Files:**
- Create: `scripts/release/package-app-artifact.sh`
- Create: `scripts/release/extract-app-artifact.sh`
- Create: `scripts/release/test-app-artifact-handoff.sh`
- Modify: `examples/app-release.yml`
- Modify: `.github/workflows/reusable-macos-release.yml`

**Interfaces:**
- `package-app-artifact.sh` consumes `APP_PATH` and `OUTPUT_ARCHIVE` and produces one `.tar.gz` containing exactly the app bundle directory.
- `extract-app-artifact.sh` consumes `ARCHIVE_PATH`, `OUTPUT_DIR`, and `APP_BASENAME`, validates member paths, extracts into `OUTPUT_DIR`, and requires the expected `.app` directory.
- The reusable release workflow changes `app_path` semantics to the relative app path after archive extraction and gains an `artifact_archive_name` input for the archive filename.

- [ ] **Step 1: Write the failing handoff test**

Create a minimal fake bundle with `Contents/MacOS/TestApp` mode `0755`, package it, simulate the downloaded archive in a clean directory, extract it, and assert `test -x` still succeeds.

```bash
fixture="${tmp}/build/TestApp.app"
mkdir -p "${fixture}/Contents/MacOS"
printf '#!/usr/bin/env bash\nexit 0\n' >"${fixture}/Contents/MacOS/TestApp"
chmod 0755 "${fixture}/Contents/MacOS/TestApp"
APP_PATH="${fixture}" OUTPUT_ARCHIVE="${tmp}/unsigned-macos-app.tar.gz" \
  bash scripts/release/package-app-artifact.sh
ARCHIVE_PATH="${tmp}/unsigned-macos-app.tar.gz" OUTPUT_DIR="${tmp}/downloaded" APP_BASENAME="TestApp.app" \
  bash scripts/release/extract-app-artifact.sh
test -x "${tmp}/downloaded/TestApp.app/Contents/MacOS/TestApp"
```

- [ ] **Step 2: Run the test to verify RED**

Run: `bash scripts/release/test-app-artifact-handoff.sh`

Expected: FAIL because the packaging/extraction scripts do not exist yet.

- [ ] **Step 3: Implement minimal package/extract scripts**

Package from the app parent directory so the archive has one stable top-level member:

```bash
tar -czf "${OUTPUT_ARCHIVE}" -C "$(dirname "${APP_PATH}")" "$(basename "${APP_PATH}")"
```

Before extraction, inspect every archive member and reject absolute paths and any `..` path component. Extract only after validation:

```bash
tar -xzf "${ARCHIVE_PATH}" -C "${OUTPUT_DIR}"
```

- [ ] **Step 4: Change the example upload to archive one file**

The build job packages `build/MyApp.app` into `build/unsigned-macos-app.tar.gz` and uploads that archive, never the `.app` directory directly.

- [ ] **Step 5: Change the reusable release workflow to extract before validation/signing**

Download the Actions artifact to `release-artifact/`, extract the configured tar archive into `release-input/`, and continue using `release-input/${{ inputs.app_path }}` for metadata/signing/DMG steps.

- [ ] **Step 6: Run shell quality and the handoff test**

Run:

```bash
bash scripts/release/test-app-artifact-handoff.sh
shellcheck scripts/release/*.sh
shfmt -d -i 2 -ci scripts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/release examples/app-release.yml .github/workflows/reusable-macos-release.yml
git commit -m "fix: preserve macOS app permissions across artifacts"
```

### Task 2: Verify the actual bundle executable

**Files:**
- Modify: `scripts/release/verify-release.sh`
- Modify: `.github/workflows/reusable-macos-release.yml`
- Modify: `scripts/release/test-app-artifact-handoff.sh`

**Interfaces:**
- Release validation reads `CFBundleExecutable` from `Contents/Info.plist` and requires `Contents/MacOS/$CFBundleExecutable` to be a regular executable file.

- [ ] **Step 1: Extend the failing fixture**

Write an XML `Info.plist` containing `CFBundleExecutable=TestApp`, then deliberately `chmod 0644` the executable and assert the verification helper rejects it.

- [ ] **Step 2: Run the fixture to verify RED**

Expected: the current verification path does not detect the mode regression.

- [ ] **Step 3: Add executable checks before signing and during final verification**

Required shell contract:

```bash
executable_name="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "${plist}")"
executable_path="${APP_PATH}/Contents/MacOS/${executable_name}"
[[ -f "${executable_path}" && -x "${executable_path}" ]]
```

For Linux fixture execution, isolate the mode check in a portable helper or test the same `-f/-x` contract directly; do not depend on `PlistBuddy` in the Linux-only fixture.

- [ ] **Step 4: Verify restored `0755` passes and `0644` fails**

Run: `bash scripts/release/test-app-artifact-handoff.sh`

Expected: PASS with both positive and negative assertions.

- [ ] **Step 5: Commit**

```bash
git add scripts/release/verify-release.sh .github/workflows/reusable-macos-release.yml scripts/release/test-app-artifact-handoff.sh
git commit -m "test: verify macOS bundle executable permissions"
```

### Task 3: Establish stable required CI contexts

**Files:**
- Modify: `.github/workflows/swift-quality.yml`
- Modify: `.github/workflows/quality.yml`
- Modify: `docs/BRANCHING.md`

**Interfaces:**
- `Swift Quality` workflow triggers on every pull request and `main` push; source detection stays inside the reusable workflow rather than at workflow trigger level.
- `Quality` exposes a final job named exactly `Required gate`, dependent on repository hygiene, secret scan, Actions security, and the release artifact handoff fixture.

- [ ] **Step 1: Remove workflow-level `paths:` filters from Swift Quality**

Keep the existing `pull_request`, `push.branches: [main]`, and `workflow_dispatch` triggers so the required check context is always created.

- [ ] **Step 2: Add an actual Actions Artifact round-trip job pair**

The producer job creates a fixture app, runs `package-app-artifact.sh`, and uploads only the `.tar.gz`. The consumer downloads the artifact, extracts it with `extract-app-artifact.sh`, and asserts the executable bit remains set.

- [ ] **Step 3: Add final `Required gate` job**

Use `if: ${{ always() }}` and fail unless every required dependency result is `success`.

```bash
[[ "${REPOSITORY_HYGIENE}" == success ]]
[[ "${SECRET_SCAN}" == success ]]
[[ "${ACTIONS_SECURITY}" == success ]]
[[ "${RELEASE_HANDOFF}" == success ]]
```

- [ ] **Step 4: Document the Ruleset contexts**

After the workflow runs once, require the observed `Quality / Required gate` and `Swift Quality / Swift quality` contexts. Solo profile remains zero approvals, conversation resolution enabled, linear history enabled, and only `main` is covered by the branch Ruleset.

- [ ] **Step 5: Validate Actions syntax/security**

Run `actionlint`, `zizmor`, ShellCheck, and shfmt through the repository Quality workflow.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows docs/BRANCHING.md
git commit -m "ci: add stable required quality gate"
```

### Task 4: Verify and open the remediation PR

**Files:**
- No production files beyond Tasks 1-3.

**Interfaces:**
- The PR remains independent from Draft PR #2 so the release/security fix can merge first.

- [ ] **Step 1: Verify branch CI**

Required green workflows: `Quality` and `Swift Quality`.

- [ ] **Step 2: Inspect the exact job names emitted by GitHub**

Confirm the Ruleset can select `Quality / Required gate` and `Swift Quality / Swift quality` without guessing.

- [ ] **Step 3: Open a focused PR**

Title: `fix: harden macOS release artifact handoff and required CI gate`

The PR body must call out the root cause (Actions Artifact does not preserve executable modes when uploading `.app` directly), the archive boundary, the executable-mode verification, the artifact round-trip test, and the remaining settings-only actions.

- [ ] **Step 4: Keep Ruleset mutations explicit**

Do not claim repository settings were changed unless an administration-capable API actually changed them. Record the exact manual/import actions still required: solo approval count `0`, required checks, conversation resolution, linear history, main-only branch targeting, and a separate immutable `v*` tag Ruleset.
