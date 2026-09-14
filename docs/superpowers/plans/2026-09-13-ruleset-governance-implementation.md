# Repository Ruleset Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portable, importable GitHub Ruleset desired-state files plus an offline semantic validator and operator documentation for the Solo OSS template profile.

**Architecture:** Store portable GitHub Ruleset JSON under `rulesets/` and enforce template-specific invariants with a Python-standard-library validator. Keep repository Administration credentials out of CI; GitHub Settings import remains an explicit administrator action. Implement and test the desired-state/validator independently first, then refresh this branch from the P0 release/required-gate main branch before wiring validation into the stable Quality gate.

**Tech Stack:** GitHub Rulesets JSON, Python 3 standard library (`json`, `pathlib`, `unittest`), GitHub Actions YAML.

**Spec:** `docs/superpowers/specs/2026-09-13-ruleset-governance-design.md`

## Global Constraints

- Solo OSS default-branch ruleset targets only `~DEFAULT_BRANCH`.
- Solo OSS required approval count is exactly `0`.
- Required check contexts are exactly `Required gate` and `swift-quality / Swift quality`.
- Review-thread resolution and linear history are required.
- Deletion and non-fast-forward updates are restricted.
- Release tags matching `refs/tags/v*` are immutable after creation through update/non-fast-forward and deletion restrictions supported by GitHub Rulesets.
- `bypass_actors` remains empty in the portable default profile.
- No repository Administration token or GitHub App admin credential is added to PR CI.
- Runtime GitHub response metadata (`id`, `node_id`, `source`, `_links`, `created_at`, `updated_at`) is not stored in desired-state files.
- The validator uses Python standard library only.
- Do not claim live GitHub Settings are synchronized merely because desired-state JSON is committed.
- PR #3 must land before the desired `Required gate` check is imported into the live Ruleset.

---

## File Structure

- `rulesets/main-solo.json` — portable default-branch Solo OSS desired state.
- `rulesets/release-tags.json` — portable immutable release-tag desired state.
- `scripts/ci/validate_rulesets.py` — pure validation library/CLI; no network access.
- `scripts/ci/test_validate_rulesets.py` — `unittest` contract tests for valid and invalid rulesets.
- `docs/GITHUB_RULESETS.md` — administrator rollout, import, layering, verification, and recovery guide.
- `.github/workflows/quality.yml` — after PR #3 lands and this branch is refreshed, run ruleset tests and production validation inside the stable foundation gate.

### Validator interface

```python
class RulesetValidationError(ValueError):
    pass


def validate_main_solo(document: dict) -> list[str]:
    """Return semantic-policy errors for the Solo default-branch ruleset."""


def validate_release_tags(document: dict) -> list[str]:
    """Return semantic-policy errors for the immutable release-tag ruleset."""


def validate_file(path: pathlib.Path, profile: str) -> list[str]:
    """Load JSON and return syntax/semantic errors without mutating input."""


def main(argv: list[str] | None = None) -> int:
    """Validate canonical repository files; return 0 on success, 1 on policy errors."""
```

The CLI output format is one diagnostic per line:

```text
rulesets/main-solo.json: pull_request.required_approving_review_count must equal 0
```

---

### Task 1: Lock the validator contract with RED tests

**Files:**
- Create: `scripts/ci/test_validate_rulesets.py`
- Create later in Task 2: `scripts/ci/validate_rulesets.py`

**Interfaces:**
- Consumes: the function signatures in the Validator interface above.
- Produces: executable policy tests proving every required rejection before production implementation exists.

- [ ] **Step 1: Write the failing unit tests**

Create tests that import `validate_rulesets` and build documents in memory so failures identify semantics rather than fixture I/O.

Core valid Solo document used by tests:

```python
def valid_main_solo() -> dict:
    return {
        "name": "Solo default branch",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": True,
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": "Required gate"},
                        {"context": "swift-quality / Swift quality"},
                    ],
                },
            },
        ],
    }
```

Core valid tag document:

```python
def valid_release_tags() -> dict:
    return {
        "name": "Immutable release tags",
        "target": "tag",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {"include": ["refs/tags/v*"], "exclude": []}
        },
        "rules": [
            {"type": "update"},
            {"type": "deletion"},
        ],
    }
```

Tests must assert exact diagnostic fragments for:

```python
self.assertIn("required_approving_review_count must equal 0", errors)
self.assertIn("ref_name.include must equal ['~DEFAULT_BRANCH']", errors)
self.assertIn("required check contexts must equal", errors)
self.assertIn("required_review_thread_resolution must be true", errors)
self.assertIn("allowed_merge_methods must equal ['squash']", errors)
self.assertIn("required_linear_history rule is required", errors)
self.assertIn("bypass_actors must be empty", errors)
self.assertIn("runtime-only field 'id' is forbidden", errors)
self.assertIn("release tag update restriction is required", errors)
self.assertIn("release tag deletion restriction is required", errors)
```

Also cover malformed JSON through `validate_file` and duplicate singleton rule types such as two `pull_request` rules.

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python3 -m unittest scripts.ci.test_validate_rulesets -v
```

Expected: import/module failure because `scripts/ci/validate_rulesets.py` does not exist yet.

- [ ] **Step 3: Commit RED tests**

```bash
git add scripts/ci/test_validate_rulesets.py
git commit -m "test: define ruleset governance policy contract"
```

---

### Task 2: Implement the offline semantic validator

**Files:**
- Create: `scripts/ci/validate_rulesets.py`
- Test: `scripts/ci/test_validate_rulesets.py`

**Interfaces:**
- Consumes: in-memory `dict` documents and canonical ruleset paths.
- Produces: `validate_main_solo`, `validate_release_tags`, `validate_file`, and CLI exit behavior.

- [ ] **Step 1: Implement shared structural helpers**

Use focused helpers rather than one large conditional function:

```python
RUNTIME_ONLY_FIELDS = {
    "id", "node_id", "source", "_links", "created_at", "updated_at"
}
CANONICAL_CHECKS = {
    "Required gate",
    "swift-quality / Swift quality",
}


def rules_by_type(document: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for rule in document.get("rules", []):
        if isinstance(rule, dict) and isinstance(rule.get("type"), str):
            grouped.setdefault(rule["type"], []).append(rule)
    return grouped
```

Reject malformed top-level types cleanly instead of raising `KeyError`/`TypeError`.

- [ ] **Step 2: Implement `validate_main_solo`**

Validation includes exact target/enforcement/bypass/ref checks, singleton rule checks, PR parameters, canonical required checks, and strict status policy.

Required check extraction must ignore ordering while rejecting duplicates or missing/extra contexts:

```python
contexts = [item.get("context") for item in checks if isinstance(item, dict)]
if len(contexts) != len(set(contexts)) or set(contexts) != CANONICAL_CHECKS:
    errors.append(
        "required check contexts must equal "
        "{'Required gate', 'swift-quality / Swift quality'}"
    )
```

Do not require `integration_id` in the portable profile.

- [ ] **Step 3: Implement `validate_release_tags`**

Require target `tag`, active enforcement, empty bypass actors, exact `refs/tags/v*` condition, and mutation restrictions. Reject `pull_request` and `required_status_checks` rules on the tag profile.

For compatibility with the current GitHub import schema, the production desired-state fixture must use the GitHub-supported tag update restriction verified during implementation. If GitHub's current import/export representation uses `update`, validate `update`; if an exported current fixture represents immutable update protection differently, update the spec and tests in the same commit before production JSON is created. Do not silently guess a field name.

- [ ] **Step 4: Implement `validate_file` and CLI**

Canonical CLI behavior:

```python
CANONICAL_PROFILES = (
    (Path("rulesets/main-solo.json"), "main-solo"),
    (Path("rulesets/release-tags.json"), "release-tags"),
)
```

When no CLI paths are supplied, validate both canonical files. JSON decode failures become normal diagnostics and exit `1`; unexpected internal exceptions must not be swallowed as policy failures.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```bash
python3 -m unittest scripts.ci.test_validate_rulesets -v
```

Expected: all policy tests pass.

- [ ] **Step 6: Commit validator**

```bash
git add scripts/ci/validate_rulesets.py scripts/ci/test_validate_rulesets.py
git commit -m "feat: validate source-controlled ruleset policy"
```

---

### Task 3: Add canonical importable desired-state JSON

**Files:**
- Create: `rulesets/main-solo.json`
- Create: `rulesets/release-tags.json`
- Test: `scripts/ci/test_validate_rulesets.py`

**Interfaces:**
- Consumes: GitHub repository Ruleset import schema and Task 2 validator.
- Produces: two portable files accepted by the semantic validator and suitable for GitHub Settings import.

- [ ] **Step 1: Add a test that validates the actual canonical files**

```python
def test_canonical_repository_rulesets_are_valid(self):
    root = Path(__file__).resolve().parents[2]
    self.assertEqual(
        [],
        validate_file(root / "rulesets/main-solo.json", "main-solo"),
    )
    self.assertEqual(
        [],
        validate_file(root / "rulesets/release-tags.json", "release-tags"),
    )
```

- [ ] **Step 2: Run test and verify RED**

Expected: missing-file diagnostics for both canonical files.

- [ ] **Step 3: Create `rulesets/main-solo.json`**

Use the same contract as `valid_main_solo()` with no repository-specific IDs. Keep conditions portable through `~DEFAULT_BRANCH`.

Before committing, compare the JSON shape against GitHub's current documented/importable repository-ruleset examples and verify rule names/parameter names are current.

- [ ] **Step 4: Create `rulesets/release-tags.json`**

Target only `refs/tags/v*`, no bypass actors, and include the verified GitHub rule types that prevent mutation/deletion of existing tags while allowing initial tag creation.

- [ ] **Step 5: Run canonical validation**

```bash
python3 -m unittest scripts.ci.test_validate_rulesets -v
python3 scripts/ci/validate_rulesets.py
```

Expected: both commands exit `0`.

- [ ] **Step 6: Commit desired state**

```bash
git add rulesets scripts/ci/test_validate_rulesets.py
git commit -m "feat: add portable solo ruleset profiles"
```

---

### Task 4: Document safe import, layering, verification, and recovery

**Files:**
- Create: `docs/GITHUB_RULESETS.md`
- Modify after PR #3 main refresh if necessary: `docs/BRANCHING.md`

**Interfaces:**
- Consumes: canonical JSON and staged rollout from the spec.
- Produces: an operator procedure that never claims live state is automatically synchronized.

- [ ] **Step 1: Write the operator guide**

Required sections and exact operational ordering:

```text
1. Preconditions
2. Stage 1 — set existing Solo approval count from 1 to 0 only
3. Merge PR #3
4. Observe Required gate and swift-quality / Swift quality on main
5. Refresh governance branch from latest main
6. Import main-solo.json
7. Disable/replace the overlapping legacy main ruleset
8. Import release-tags.json
9. Inspect effective rules / Rule Insights
10. Open a harmless smoke PR
11. Recovery procedure
```

Explicit warnings:

- overlapping rulesets combine; the stricter approval=1 policy is not overridden by a newer approval=0 policy;
- do not add `Required gate` before the workflow exists successfully on `main`;
- do not test tag immutability by creating a production-like release tag in this repository;
- do not put an Administration token into ordinary PR Actions.

- [ ] **Step 2: Verify terminology against JSON**

Search the docs and JSON together for exact contexts and targets:

```bash
grep -RFn "Required gate" docs/GITHUB_RULESETS.md rulesets
 grep -RFn "swift-quality / Swift quality" docs/GITHUB_RULESETS.md rulesets
```

Expected: the same context names appear consistently.

- [ ] **Step 3: Commit documentation**

```bash
git add docs/GITHUB_RULESETS.md
git commit -m "docs: document ruleset rollout and recovery"
```

---

### Task 5: Refresh from the P0 foundation before CI wiring

**Files:**
- No intentional source changes; branch integration step.

**Interfaces:**
- Consumes: PR #3 merged `main` containing `Required gate` and always-created Swift Quality.
- Produces: governance branch whose Quality workflow includes the current stable gate implementation.

- [ ] **Step 1: Verify PR #3 is merged**

Required state:

```text
PR #3 state == merged
```

If it is still blocked by the live approval=1 rule, STOP this task. Do not work around the repository policy with a forced ref update or bypass.

- [ ] **Step 2: Verify main CI contexts exist after merge**

Observe successful main Check Runs for:

```text
Required gate
swift-quality / Swift quality
```

Do not infer context names from YAML.

- [ ] **Step 3: Refresh `feat/ruleset-governance` from latest main**

Use the repository's approved branch-integration method. Resolve conflicts by preserving the PR #3 stable gate implementation and the governance spec/validator work. Do not force-update `main`.

- [ ] **Step 4: Re-run governance unit tests after refresh**

```bash
python3 -m unittest scripts.ci.test_validate_rulesets -v
python3 scripts/ci/validate_rulesets.py
```

Expected: PASS.

---

### Task 6: Wire Ruleset validation into the stable Quality gate

**Files:**
- Modify: `.github/workflows/quality.yml`

**Interfaces:**
- Consumes: PR #3's `repository-hygiene` / `Required gate` topology and Task 2 validator.
- Produces: ruleset policy validation that runs on every Quality execution and is transitively enforced by `Required gate`.

- [ ] **Step 1: Add governance validation to `repository-hygiene`**

After shell/workflow formatting checks, add:

```yaml
      - name: Ruleset governance tests
        shell: bash
        run: |
          set -euo pipefail
          python3 -m unittest scripts.ci.test_validate_rulesets -v
          python3 scripts/ci/validate_rulesets.py
```

Do not add a workflow-level `paths:` filter.

- [ ] **Step 2: Run/observe CI and verify the stable gate remains stable**

Expected latest-head results:

```text
Repository hygiene: success
Secret scan: success
GitHub Actions security: success
Release artifact permission roundtrip: success
Required gate: success
Swift Quality: success
```

Also inspect Check Runs and confirm the external Ruleset context remains exactly `Required gate` rather than introducing a renamed required context.

- [ ] **Step 3: Commit Quality integration**

```bash
git add .github/workflows/quality.yml
git commit -m "ci: enforce ruleset governance policy"
```

---

### Task 7: Final verification and PR update

**Files:**
- Modify: PR #4 metadata only after implementation is complete.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: review-ready PR that accurately separates desired state from live GitHub Settings.

- [ ] **Step 1: Run fresh repository verification**

Required checks:

```bash
python3 -m unittest scripts.ci.test_validate_rulesets -v
python3 scripts/ci/validate_rulesets.py
```

And latest-head GitHub Actions:

```text
Quality: success
Swift Quality: success
Required gate: success
```

- [ ] **Step 2: Inspect PR diff for forbidden scope**

Ensure the PR contains no:

```text
PAT/admin secret
workflow that writes live Rulesets
automatic Ruleset API mutation
Team profile
repository-specific Ruleset IDs
claim that live Settings are synchronized
```

- [ ] **Step 3: Update PR #4 title/body**

Final title:

```text
feat: add source-controlled ruleset governance
```

PR body must identify:

- the two desired-state files;
- validator/TDD coverage;
- Quality integration;
- safe rollout dependency on PR #3;
- live Settings still requiring administrator import;
- current live state separately from desired state.

- [ ] **Step 4: Request review and keep merge blocked until live rollout prerequisite is satisfied**

Do not merge PR #4 ahead of PR #3. Do not enable live required `Required gate` until the successful main context exists.
