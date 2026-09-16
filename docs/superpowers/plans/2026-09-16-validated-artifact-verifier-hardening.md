# Validated Artifact Verifier Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the validator-to-signer artifact trust boundary directly testable and prove that an artifact from a previous publisher attempt is rejected before entering the release Environment.

**Architecture:** Move the current inline validated-artifact identity checks out of `.github/workflows/reusable-macos-release.yml` into a small trusted Python verifier plus CLI wrapper. The verifier derives the canonical handoff name from publisher/source run identities, validates exact Artifact ID/name/digest/expiration/current publisher run binding, and remains invoked before download/signing. Workflow contract tests require use of the trusted verifier; unit tests exercise previous-attempt rejection explicitly.

**Tech Stack:** Python 3 standard library, `unittest`, Bash/GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-09-14-privileged-release-isolation-review-addendum.md`

## Global Constraints

- The validator handoff remains unique to publisher run ID **and run attempt**.
- The privileged job must reject fallback to an artifact from an older publisher attempt.
- No secrets are introduced into the validation boundary.
- The reusable release job continues to verify artifact identity before downloading and before certificate import.
- No `pull_request_target`, bypass actor, or administration-token shortcut is introduced.

---

### Task 1: Add RED acceptance tests for the validated artifact boundary

**Files:**
- Create: `scripts/release/test_validated_artifact.py`
- Modify: `scripts/release/test_privileged_release_workflow_contract.py`
- Modify: `.github/workflows/release-isolation-tdd.yml`

**Interfaces:**
- Consumes: current reusable release workflow inputs `validated_artifact_id`, `validated_artifact_name`, `validated_artifact_digest`, source run ID/attempt, and publisher run ID/attempt.
- Produces: tests requiring `scripts/release/verify-validated-artifact.py` and explicit rejection of a previous publisher attempt.

- [ ] **Step 1: Write a failing behavioral test**

Create tests that expect a pure verifier API:

```python
errors = verify_validated_artifact(
    artifact_metadata=document,
    artifact_id=7001,
    artifact_name="validated-release-input-99887766-4-123456789-2",
    artifact_digest="sha256:" + "a" * 64,
    publisher_run_id=99887766,
    publisher_run_attempt=4,
    source_run_id=123456789,
    source_run_attempt=2,
)
assert errors == []
```

and mutate the metadata/name to publisher attempt `3`; the verifier must return an error mentioning the canonical artifact name/current publisher attempt.

- [ ] **Step 2: Add a workflow contract test**

Require `.github/workflows/reusable-macos-release.yml` to call `scripts/release/verify-validated-artifact.py` before `actions/download-artifact`, and require the verifier step to receive current `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, source run ID/attempt, Artifact ID/name/digest.

- [ ] **Step 3: Add the new unit-test module to Release Isolation TDD**

Add `scripts.release.test_validated_artifact` to the explicit `python3 -m unittest` list.

- [ ] **Step 4: Run CI and verify RED**

Expected: `Release Isolation TDD` fails because `scripts.release.validated_artifact` / `verify-validated-artifact.py` do not exist and the reusable workflow still contains inline validation.

---

### Task 2: Implement the trusted validated-artifact verifier

**Files:**
- Create: `scripts/release/validated_artifact.py`
- Create: `scripts/release/verify-validated-artifact.py`

**Interfaces:**
- Produces: `verify_validated_artifact(...) -> list[str]`.
- CLI consumes an Artifact API metadata JSON file plus exact expected IDs/digest/run identities and exits nonzero on any trust mismatch.

- [ ] **Step 1: Implement canonical name derivation**

```python
def canonical_validated_artifact_name(
    publisher_run_id: int,
    publisher_run_attempt: int,
    source_run_id: int,
    source_run_attempt: int,
) -> str:
    return (
        f"validated-release-input-{publisher_run_id}-{publisher_run_attempt}-"
        f"{source_run_id}-{source_run_attempt}"
    )
```

- [ ] **Step 2: Implement fail-closed metadata verification**

Validate positive integer IDs/attempts, canonical `sha256:<64 lowercase hex>` digest, caller-supplied artifact name equals the derived canonical name, API metadata `id/name/digest`, `expired is False`, and `workflow_run.id == publisher_run_id`.

- [ ] **Step 3: Implement the CLI wrapper**

Parse arguments, load JSON strictly as an object, call the pure verifier, print each error to stderr, and exit `1` on validation failure / `0` on success.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: valid artifact passes; previous publisher attempt, wrong ID, wrong digest, expired artifact, malformed workflow-run metadata all fail closed.

---

### Task 3: Replace inline workflow validation with the trusted verifier

**Files:**
- Modify: `.github/workflows/reusable-macos-release.yml`

**Interfaces:**
- Consumes: current workflow inputs and GitHub Artifact API response.
- Produces: unchanged downstream artifact download/signing behavior after a stronger testable pre-download boundary.

- [ ] **Step 1: Keep the API fetch in the secret-free pre-download step**

Fetch `/repos/${GITHUB_REPOSITORY}/actions/artifacts/${VALIDATED_ARTIFACT_ID}` into a temporary JSON file using the existing read-only `GITHUB_TOKEN`.

- [ ] **Step 2: Invoke the trusted verifier**

Pass Artifact ID/name/digest, current publisher run ID/attempt, and source run ID/attempt to `scripts/release/verify-validated-artifact.py`.

- [ ] **Step 3: Remove the duplicated inline Python validator**

Keep only orchestration in YAML; trust logic lives in the tested Python module.

- [ ] **Step 4: Run fresh exact-head CI**

Require `Release Isolation TDD`, `Quality` including `Required gate`, and `Swift Quality` all to succeed, with zero unresolved review threads.

---

### Task 4: Update PR evidence

**Files:**
- PR #6 body / Issue #17 checkpoint only.

- [ ] **Step 1: Record RED and GREEN SHAs/run numbers**
- [ ] **Step 2: Record the explicit previous-attempt rejection acceptance test**
- [ ] **Step 3: Re-read the live Ruleset before any merge action**
