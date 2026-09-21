# Validated Artifact Verifier Hardening Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the publisher-owned validated artifact check into a directly testable, fail-closed trust-boundary verifier that rejects stale publisher attempts and binds the artifact to the trusted publisher source/repository before privileged release consumption.

**Architecture:** Keep GitHub API access and artifact download in the privileged reusable workflow, but move metadata validation into a small pure Python module plus CLI. The workflow fetches the exact Artifact API object by ID, the verifier checks canonical artifact naming, current publisher run/attempt, publisher SHA, repository identity, digest, expiration state, and source-run binding, and only then may `actions/download-artifact` consume it. No secrets are introduced into validation and no release policy is read from the validated artifact.

**Tech Stack:** Python 3 standard library, GitHub Actions YAML, existing `Release Isolation TDD` workflow, existing `quality.yml` release-isolation contract.

---

### Task 1: Add failing validated-artifact trust-boundary tests

**Files:**
- Modify: `scripts/release/test_validated_artifact.py`
- Modify: `scripts/release/test_privileged_release_workflow_contract.py`

**Step 1: Write the failing behavior tests**

Cover:
- exact current publisher attempt is accepted;
- previous publisher attempt is rejected;
- wrong Artifact ID is rejected;
- wrong Artifact digest is rejected;
- expired Artifact is rejected;
- Artifact `workflow_run.id` drift is rejected;
- Artifact `workflow_run.head_sha` drift is rejected;
- Artifact `workflow_run.repository_id` drift is rejected;
- Artifact `workflow_run.head_repository_id` drift is rejected;
- malformed expected IDs/digests/SHAs are rejected;
- workflow invokes the trusted verifier before `actions/download-artifact` and passes publisher run/attempt/SHA plus canonical repository ID.

**Step 2: Verify RED**

Run via the `Release Isolation TDD` workflow. Confirm only the new contract fails because the verifier/API binding is missing.

**Step 3: Commit RED**

Historical REDs:
- `42fd87a478a4a7297986890e61ea00579e385609` — initial current-attempt verifier extraction contract.
- `c193206cd6b18045f43b67e4a0a2aa04aea26894` — publisher SHA/repository binding contract; Release Isolation TDD #108 ran 98 tests and failed only the new binding assertions.

### Task 2: Implement the pure verifier and CLI

**Files:**
- Create/Modify: `scripts/release/validated_artifact.py`
- Create/Modify: `scripts/release/verify-validated-artifact.py`
- Modify: `scripts/release/test_validated_artifact.py`

**Step 1: Implement canonical naming**

Artifact name must be exactly:

`validated-release-input-<publisher_run_id>-<publisher_run_attempt>-<source_run_id>-<source_run_attempt>`

**Step 2: Implement fail-closed metadata checks**

Require:
- positive integer Artifact ID / run IDs / attempts / repository ID;
- exact canonical name;
- lowercase `sha256:<64 hex>` digest;
- `expired == false`;
- `workflow_run.id == current publisher run ID`;
- `workflow_run.head_sha == trusted publisher SHA`;
- `workflow_run.repository_id == current repository ID`;
- `workflow_run.head_repository_id == current repository ID`.

Any missing/malformed/drifted field is an error.

**Step 3: Implement CLI**

CLI accepts metadata file plus trusted expected values and exits non-zero with diagnostics when any check fails.

### Task 3: Wire trusted verifier before download

**Files:**
- Modify: `.github/workflows/reusable-macos-release.yml`
- Modify: `scripts/release/test_privileged_release_workflow_contract.py`

**Step 1: Fetch exact Artifact API object**

Use `gh api /repos/${GITHUB_REPOSITORY}/actions/artifacts/${VALIDATED_ARTIFACT_ID}` with the existing `actions: read` permission.

**Step 2: Validate before `actions/download-artifact`**

Pass:
- expected artifact ID/name/digest;
- current publisher run ID/attempt;
- current publisher SHA;
- current repository ID;
- validated source run ID/attempt.

Only after successful validation may the artifact be downloaded.

### Task 4: Verify GREEN and record evidence

**Step 1: Release Isolation TDD**

Expected: all release provenance / artifact layout / resolver / source-binding tests succeed.

**Step 2: Quality**

Expected: actionlint, ShellCheck, shfmt, zizmor, Gitleaks, release isolation contract, handoff regressions, permission roundtrip, and `Required gate` succeed.

**Step 3: Swift Quality**

Expected: Swift policy remains unaffected and succeeds.

**Step 4: Record evidence**

Implementation GREEN commit:
`3a1e268bb369d4ee2e84f9fb7557b742dac42f98`

The plan-document update that records this result intentionally moves the branch head beyond the implementation commit; PR-level exact-head CI is the authoritative freshness evidence.

### Safety invariants

- validation remains secret-free;
- privileged credentials remain inside the `release` Environment;
- no `pull_request_target` path is introduced;
- source/tag policy is not derived from artifact contents;
- exact Artifact ID/digest plus publisher run/attempt/SHA and repository ID are all revalidated before download;
- previous publisher attempts fail closed;
- release enablement remains blocked until governance and Environment rollout prerequisites are satisfied.
