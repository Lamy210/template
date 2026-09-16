# Test Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add backward-compatible named test-policy profiles that normalize into the existing classifier and Required Gate without duplicating workflows.

**Architecture:** Introduce `resolve-test-profile.py` immediately before `classify-test-policy.py`. The resolver owns preset/default/override parsing; the classifier remains the semantic invariant checker. Existing `MACOS_*` variables remain the low-level interface and no-profile mode preserves current behavior.

**Tech Stack:** Python 3 standard library, `unittest`, GitHub Actions YAML, existing repository CI scripts.

**Spec:** `docs/superpowers/specs/2026-09-16-test-profiles-adoption-design.md`

## Global Constraints

- Begin implementation only after PRs #2 through #16 are landed on `main` and post-landing CI is green.
- `MACOS_TEST_PROFILE` accepts only empty, `minimal`, `standard`, `macos-app`, or `macos-ui-strict`.
- No-profile behavior is backward-compatible.
- Existing `MACOS_*` values override profile defaults independently; the resolver never changes a second field to repair a conflict.
- `macos-app` and `macos-ui-strict` require adapter `xcode`.
- Integration is disabled by every preset.
- Visual bootstrap is false unless explicitly enabled.
- Unknown profiles and malformed non-empty booleans fail closed.
- No `pull_request_target`, secrets, or write permissions are introduced.

---

### Task 1: Add the profile resolver with RED-first tests

**Files:**
- Create: `scripts/test/resolve-test-profile.py`
- Create: `scripts/test/test-resolve-test-profile.py`

**Interfaces:**
- CLI: `resolve-test-profile.py (--from-env | --input PATH) --output PATH`.
- JSON input uses `null` for unset boolean overrides.
- Output contains exactly the current classifier keys.

- [ ] **Step 1: Write the failing test module**

Use `importlib.util.spec_from_file_location` to load the hyphenated production script once it exists. Define this test helper in the test module so every case has a complete payload:

```python
def payload(
    *,
    profile: str,
    adapter: str,
    integration_enabled: bool | None = None,
    integration_required: bool | None = None,
    coverage_enabled: bool | None = None,
    coverage_required: bool | None = None,
    e2e_enabled: bool | None = None,
    e2e_required: bool | None = None,
    visual_enabled: bool | None = None,
    visual_required: bool | None = None,
    visual_bootstrap: bool | None = None,
) -> dict[str, object]:
    return {
        "profile": profile,
        "adapter": adapter,
        "integrationEnabled": integration_enabled,
        "integrationRequired": integration_required,
        "coverageEnabled": coverage_enabled,
        "coverageRequired": coverage_required,
        "e2eEnabled": e2e_enabled,
        "e2eRequired": e2e_required,
        "visualEnabled": visual_enabled,
        "visualRequired": visual_required,
        "visualBootstrap": visual_bootstrap,
    }
```

Assert these exact preset expectations:

```python
EXPECTED = {
    "minimal": (False, False, False, False, False, False, False, False, False),
    "standard": (False, False, True, True, False, False, False, False, False),
    "macos-app": (False, False, True, True, True, True, False, False, False),
    "macos-ui-strict": (False, False, True, True, True, True, True, True, False),
}
```

Tuple order is Integration enabled/required, Coverage enabled/required, E2E enabled/required, Visual enabled/required, Visual bootstrap.

Also add these behavior tests:

```python
def test_legacy_coverage_enabled_defaults_required_true(self):
    result = resolver.resolve(payload(
        profile="", adapter="swiftpm", coverage_enabled=True
    ))
    self.assertTrue(result["coverageEnabled"])
    self.assertTrue(result["coverageRequired"])


def test_macos_app_e2e_can_be_made_optional(self):
    result = resolver.resolve(payload(
        profile="macos-app", adapter="xcode", e2e_required=False
    ))
    self.assertTrue(result["e2eEnabled"])
    self.assertFalse(result["e2eRequired"])


def test_disabling_e2e_does_not_implicitly_clear_required(self):
    result = resolver.resolve(payload(
        profile="macos-app", adapter="xcode", e2e_enabled=False
    ))
    self.assertFalse(result["e2eEnabled"])
    self.assertTrue(result["e2eRequired"])
```

Cover invalid profile, invalid non-empty boolean environment value, Xcode-only profile with SwiftPM, explicit Visual bootstrap, and legacy Visual enabled→required default.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/test/test-resolve-test-profile.py -v
```

Expected: missing production script/import failure.

- [ ] **Step 3: Implement resolver data tables and parsing**

Production constants:

```python
PROFILE_NAMES = {"minimal", "standard", "macos-app", "macos-ui-strict"}
XCODE_ONLY_PROFILES = {"macos-app", "macos-ui-strict"}
OVERRIDE_FIELDS = (
    "integrationEnabled", "integrationRequired",
    "coverageEnabled", "coverageRequired",
    "e2eEnabled", "e2eRequired",
    "visualEnabled", "visualRequired", "visualBootstrap",
)
```

`PROFILES` must encode the exact table from the spec. Implement:

```python
def parse_optional_bool(value: object, field: str) -> bool | None:
    if value is None or value == "":
        return None
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise InputError(f"{field} must be true, false, or empty")
```

`load_environment()` reads profile, adapter, and existing `MACOS_*` policy variables. `resolve(payload)` validates profile/adapter compatibility, starts from the selected profile defaults or exact legacy defaults, then applies every non-`None` override independently.

Legacy requiredness rules must match current behavior: Coverage required when enabled unless explicitly false; Visual required when enabled unless explicitly false; Integration and E2E required only when explicitly true.

- [ ] **Step 4: Implement deterministic CLI output**

Use mutually exclusive `--from-env` / `--input`, required `--output`, UTF-8 JSON with `indent=2`, `sort_keys=True`, and trailing newline. The output object contains only:

```text
adapter
integrationEnabled
integrationRequired
coverageEnabled
coverageRequired
e2eEnabled
e2eRequired
visualEnabled
visualRequired
visualBootstrap
```

- [ ] **Step 5: Run tests and compile checks**

```bash
python3 -m unittest scripts/test/test-resolve-test-profile.py -v
python3 -m py_compile scripts/test/resolve-test-profile.py scripts/test/test-resolve-test-profile.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/test/resolve-test-profile.py scripts/test/test-resolve-test-profile.py
git commit -m "feat(test): add test profile resolver"
```

---

### Task 2: Prove profiles cannot bypass classifier invariants

**Files:**
- Modify: `scripts/test/test-resolve-test-profile.py`
- Modify: `scripts/test/test-classify-test-policy.py`

**Interfaces:**
- Production resolver output feeds production `classify()` unchanged.

- [ ] **Step 1: Add a reusable production-module loader to the test file**

```python
def load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
```

Load both resolver and classifier from their repository files; never copy their algorithms into the tests.

- [ ] **Step 2: Add resolve→classify behavior tests**

```python
def test_profile_required_while_disabled_is_rejected(self):
    resolved = resolver.resolve(payload(
        profile="macos-app", adapter="xcode", e2e_enabled=False
    ))
    code, classified = classifier.classify(resolved)
    self.assertEqual(code, classifier.EXIT_CONFIGURATION_ERROR)
    self.assertIn("E2E cannot be required while disabled", classified["errors"])


def test_visual_profile_still_requires_e2e(self):
    resolved = resolver.resolve(payload(
        profile="macos-ui-strict",
        adapter="xcode",
        e2e_enabled=False,
        e2e_required=False,
    ))
    code, classified = classifier.classify(resolved)
    self.assertEqual(code, classifier.EXIT_CONFIGURATION_ERROR)
    self.assertIn("Visual requires E2E to be enabled", classified["errors"])
```

- [ ] **Step 3: Run combined suites**

```bash
python3 -m unittest scripts/test/test-resolve-test-profile.py scripts/test/test-classify-test-policy.py -v
```

Expected: PASS with the new conflict tests proving the resolver does not normalize invalid overrides into success.

- [ ] **Step 4: Commit**

```bash
git add scripts/test/test-resolve-test-profile.py scripts/test/test-classify-test-policy.py
git commit -m "test(test): enforce profile classifier boundary"
```

---

### Task 3: Wire profile resolution into `Tests` without changing downstream topology

**Files:**
- Modify: `.github/workflows/tests.yml`
- Create: `scripts/test/test-test-profile-wiring.py`
- Modify: `.github/workflows/test-infrastructure.yml`

**Interfaces:**
- `classify` job gains profile resolution.
- Existing classifier outputs and downstream `needs.classify.outputs.*` remain unchanged.

- [ ] **Step 1: Write the workflow contract test first**

Assert:

```python
self.assertIn("MACOS_TEST_PROFILE: ${{ vars.MACOS_TEST_PROFILE }}", workflow)
self.assertIn("python3 scripts/test/resolve-test-profile.py", workflow)
self.assertIn("--from-env", workflow)
self.assertIn("--output \"${RUNNER_TEMP}/test-policy.json\"", workflow)
self.assertIn("python3 scripts/test/classify-test-policy.py", workflow)
self.assertIn("--input \"${RUNNER_TEMP}/test-policy.json\"", workflow)
for stable_name in (
    "Unit runner", "Integration runner", "E2E runner", "Visual runner",
    "Coverage", "Tests / Required Gate",
):
    self.assertIn(stable_name, workflow)
```

Also assert the old classifier direct `--from-env` invocation is absent.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/test/test-test-profile-wiring.py -v
```

- [ ] **Step 3: Modify only the classify path**

Add `MACOS_TEST_PROFILE` to `env`, then use:

```yaml
- name: Resolve test profile
  shell: bash
  run: >-
    python3 scripts/test/resolve-test-profile.py
    --from-env
    --output "${RUNNER_TEMP}/test-policy.json"

- name: Classify configured test subsystems
  id: policy
  shell: bash
  run: >-
    python3 scripts/test/classify-test-policy.py
    --input "${RUNNER_TEMP}/test-policy.json"
    --github-output "$GITHUB_OUTPUT"
```

Do not change Unit/Integration/E2E/Visual/Coverage proxy semantics in this PR.

- [ ] **Step 4: Add new tests to Test Infrastructure**

Run resolver, classifier, and profile-wiring tests in the existing Test Infrastructure job.

- [ ] **Step 5: Run policy verification**

```bash
python3 -m unittest \
  scripts/test/test-resolve-test-profile.py \
  scripts/test/test-classify-test-policy.py \
  scripts/test/test-test-profile-wiring.py \
  scripts/test/test-evaluate-required-gate.py \
  scripts/test/test-required-gate-workflow.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/tests.yml .github/workflows/test-infrastructure.yml scripts/test/test-test-profile-wiring.py
git commit -m "feat(ci): resolve named test profiles"
```

---

### Task 4: Document profile-first adoption and finish the PR

**Files:**
- Create: `docs/TEST_PROFILES.md`
- Modify: `README.md`
- Modify: `docs/SETUP.md`

- [ ] **Step 1: Add exact profile documentation**

Include the four-profile table, adapter requirements, independent override rule, legacy mode, and these examples:

```text
MACOS_TEST_PROFILE=standard
MACOS_TEST_ADAPTER=swiftpm
```

```text
MACOS_TEST_PROFILE=macos-app
MACOS_TEST_ADAPTER=xcode
MACOS_E2E_REQUIRED=false
```

Document that `MACOS_E2E_ENABLED=false` alone under `macos-app` is intentionally invalid because the profile still requires E2E.

- [ ] **Step 2: Update README Adoption**

Put profile-first setup before the existing low-level manual interface. Do not remove advanced manual configuration.

- [ ] **Step 3: Update SETUP**

Add `MACOS_TEST_PROFILE` repository-variable guidance and retain the existing manual Ruleset/Environment/Secret steps.

- [ ] **Step 4: Run exact-head verification**

Run local policy suites, then require fresh successful Quality, Tests, and Test Infrastructure workflows on the PR exact head. Verify zero unresolved review threads.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md docs/SETUP.md docs/TEST_PROFILES.md
git commit -m "docs: document test policy profiles"
```
