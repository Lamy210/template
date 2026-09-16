# Setup UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic local setup command that turns the proven profile contract into a validated adopter configuration without mutating privileged GitHub administration state.

**Architecture:** Implement a Python setup tool that validates profile/adapter/project inputs, writes `.template/config.json`, and renders exact `gh variable set` commands plus a manual GitHub Settings checklist. Reuse production profile resolution and classifier code instead of duplicating policy.

**Tech Stack:** Python 3 standard library, `unittest`, existing profile resolver/classifier.

**Spec:** `docs/superpowers/specs/2026-09-16-test-profiles-adoption-design.md`

## Global Constraints

- Begin only after the Adoption Runtime PR is merged and all four profile runtime fixtures are green on `main`.
- Setup remains local-only; it never mutates Rulesets, Environments, Secrets, branch protection, or repository settings.
- Never accept secret values as CLI options and never write secrets to disk.
- Keep the direct low-level `MACOS_*` interface supported and documented.
- Generated JSON is deterministic and atomically replaced.
- Unknown profile/adapter, unsafe paths, invalid Xcode topology, and profile/classifier conflicts fail before writing config.

---

### Task 1: Add validated schema/config generation

**Files:**
- Create: `scripts/setup/configure-template.py`
- Create: `scripts/setup/test-configure-template.py`
- Create: `.template/.gitkeep`

**Interfaces:**
- CLI: `configure-template.py --profile NAME --adapter NAME --working-directory PATH [--project-path PATH | --workspace-path PATH] [--scheme NAME] [--output PATH] --non-interactive`
- Default output: `.template/config.json`
- Schema version: 1

- [ ] **Step 1: Write failing tests**

Expected SwiftPM JSON:

```json
{
  "schemaVersion": 1,
  "test": {
    "adapter": "swiftpm",
    "profile": "standard",
    "projectPath": "",
    "scheme": "",
    "workingDirectory": ".",
    "workspacePath": ""
  }
}
```

Add tests for:

```python
def test_swiftpm_standard_config(self):
    self.assertEqual(
        build_config(
            profile="standard",
            adapter="swiftpm",
            working_directory=".",
            project_path="",
            workspace_path="",
            scheme="",
        )["test"]["profile"],
        "standard",
    )


def test_xcode_requires_exactly_one_container(self):
    with self.assertRaises(ConfigError):
        build_config(
            profile="macos-app",
            adapter="xcode",
            working_directory=".",
            project_path="",
            workspace_path="",
            scheme="App",
        )
```

Also cover absolute path, `..`, unknown profile/adapter, both project+workspace, and empty Xcode scheme.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/setup/test-configure-template.py -v
```

Expected: missing implementation failure.

- [ ] **Step 3: Implement path/config validation**

Use these production functions:

```python
class ConfigError(ValueError):
    pass


def safe_relative_path(value: str, *, allow_dot: bool = True) -> str:
    path = Path(value)
    if not value or "\x00" in value or path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"unsafe repository-relative path: {value!r}")
    if value == "." and not allow_dot:
        raise ConfigError("'.' is not allowed here")
    return value


def build_config(
    *,
    profile: str,
    adapter: str,
    working_directory: str,
    project_path: str,
    workspace_path: str,
    scheme: str,
) -> dict[str, object]:
    if profile not in {"minimal", "standard", "macos-app", "macos-ui-strict"}:
        raise ConfigError(f"unsupported profile: {profile}")
    if adapter not in {"swiftpm", "xcode"}:
        raise ConfigError(f"unsupported adapter: {adapter}")
    safe_relative_path(working_directory)
    if adapter == "swiftpm":
        if project_path or workspace_path or scheme:
            raise ConfigError("SwiftPM config cannot include Xcode container or scheme")
    else:
        if bool(project_path) == bool(workspace_path):
            raise ConfigError("Xcode config requires exactly one project or workspace")
        safe_relative_path(project_path or workspace_path, allow_dot=False)
        if not scheme:
            raise ConfigError("Xcode config requires scheme")
    return {
        "schemaVersion": 1,
        "test": {
            "adapter": adapter,
            "profile": profile,
            "projectPath": project_path,
            "scheme": scheme,
            "workingDirectory": working_directory,
            "workspacePath": workspace_path,
        },
    }
```

- [ ] **Step 4: Reuse production resolver/classifier before write**

Convert the config to resolver input with all subsystem overrides `None`; call production resolver and classifier functions through `importlib.util.spec_from_file_location`. If either rejects the configuration, raise `ConfigError` and do not touch the output path.

- [ ] **Step 5: Implement atomic deterministic JSON write**

Serialize `indent=2`, `sort_keys=True`, UTF-8, one trailing newline into a temporary sibling path, `flush`, `os.fsync`, then `os.replace` onto the destination.

- [ ] **Step 6: Run tests/compile checks**

```bash
python3 -m unittest scripts/setup/test-configure-template.py -v
python3 -m py_compile scripts/setup/configure-template.py scripts/setup/test-configure-template.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/setup .template/.gitkeep
git commit -m "feat(setup): add validated template config"
```

---

### Task 2: Render repository variables and manual GitHub checklist

**Files:**
- Create: `scripts/setup/render-setup-summary.py`
- Create: `scripts/setup/test-render-setup-summary.py`
- Modify: `scripts/setup/configure-template.py`

**Interfaces:**
- CLI: `render-setup-summary.py --config PATH`
- Renders commands only; never invokes `gh`.

- [ ] **Step 1: Write failing renderer tests**

Require exact SwiftPM lines:

```text
gh variable set MACOS_TEST_PROFILE --body standard
gh variable set MACOS_TEST_ADAPTER --body swiftpm
gh variable set MACOS_TEST_WORKING_DIRECTORY --body .
```

For Xcode require exact selected container/scheme lines. Assert Apple secret names are mentioned only in the manual checklist, never rendered with values.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/setup/test-render-setup-summary.py -v
```

- [ ] **Step 3: Implement exact variable mapping**

Use:

```python
VARIABLE_MAP = (
    ("MACOS_TEST_PROFILE", "profile"),
    ("MACOS_TEST_ADAPTER", "adapter"),
    ("MACOS_TEST_WORKING_DIRECTORY", "workingDirectory"),
    ("MACOS_TEST_PROJECT_PATH", "projectPath"),
    ("MACOS_TEST_WORKSPACE_PATH", "workspacePath"),
    ("MACOS_TEST_SCHEME", "scheme"),
)
```

Skip only empty optional values. Quote values with `shlex.quote`.

- [ ] **Step 4: Render sections in fixed order**

Output headings:

```text
Resolved test profile
Repository variables
Manual GitHub Settings
Release Environment and Secrets
Verification
```

Manual Settings states Solo OSS approvals=0, required checks are selected after observed successful runs, immutable `v*` Ruleset is release-only, and protected `release` Environment is release-only.

- [ ] **Step 5: Add configure command output modes**

Add `--summary` and `--print-commands` that call the renderer after successful config validation/write. No remote execution path is added.

- [ ] **Step 6: Run tests and commit**

```bash
python3 -m unittest scripts/setup/test-configure-template.py scripts/setup/test-render-setup-summary.py -v
git add scripts/setup
git commit -m "feat(setup): render repository setup commands"
```

---

### Task 3: Add deterministic interactive input

**Files:**
- Modify: `scripts/setup/configure-template.py`
- Modify: `scripts/setup/test-configure-template.py`

**Interfaces:**
- Interactive mode uses injected stdin/stdout functions for testability.
- `--non-interactive` remains the stable automation interface.

- [ ] **Step 1: Write RED prompt-flow tests**

Define production signature:

```python
def collect_interactive_config(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> dict[str, str]:
```

Test SwiftPM flow, Xcode project flow, Xcode workspace flow, invalid-profile retry, and confirmation rejection.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/setup/test-configure-template.py -v
```

- [ ] **Step 3: Implement fixed prompt sequence**

Prompt profile (`standard` default), adapter (`swiftpm` default), working directory (`.` default), then for Xcode ask project/workspace, selected relative path, scheme, and final yes/no confirmation. Loop only on invalid enumerated answers; EOF/negative confirmation exits nonzero without writing config.

- [ ] **Step 4: Add byte-stability regression**

Run the same explicit noninteractive flags before/after interactive support and assert generated JSON bytes are identical.

- [ ] **Step 5: Run all setup tests and commit**

```bash
python3 -m unittest discover -s scripts/setup -p 'test-*.py' -v
git add scripts/setup/configure-template.py scripts/setup/test-configure-template.py
git commit -m "feat(setup): add interactive profile setup"
```

---

### Task 4: Verify generated config against repository files and production policy

**Files:**
- Create: `scripts/setup/verify-template-config.py`
- Create: `scripts/setup/test-verify-template-config.py`
- Modify: `.github/workflows/test-infrastructure.yml`

**Interfaces:**
- CLI: `verify-template-config.py --config PATH`
- Checks schema/filesystem/profile/classifier; it does not compile the app.

- [ ] **Step 1: Write RED verifier tests**

Cover valid SwiftPM adoption fixture, valid Xcode adoption fixture, missing working dir, missing `Package.swift`, missing Xcode project/workspace, empty scheme, unsupported schema version, and profile/classifier conflict.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest scripts/setup/test-verify-template-config.py -v
```

- [ ] **Step 3: Implement filesystem checks**

For SwiftPM require `<root>/<workingDirectory>/Package.swift`. For Xcode require exactly the selected `.xcodeproj` or `.xcworkspace` directory and non-empty scheme. Reject symlink escape by resolving both repository root and candidate path and requiring the candidate remain under root.

- [ ] **Step 4: Re-run production policy validation**

Construct resolver input from the config, call resolver then classifier, and print normalized policy on success. Any configurationError exits nonzero.

- [ ] **Step 5: Wire setup tests into Test Infrastructure**

Run `python3 -m unittest discover -s scripts/setup -p 'test-*.py' -v` on Ubuntu when `scripts/setup/**`, `.template/**`, resolver/classifier, or setup docs change.

- [ ] **Step 6: Run and commit**

```bash
python3 -m unittest discover -s scripts/setup -p 'test-*.py' -v
python3 -m unittest scripts/test/test-resolve-test-profile.py scripts/test/test-classify-test-policy.py -v
git add scripts/setup .github/workflows/test-infrastructure.yml
git commit -m "test(setup): verify generated template config"
```

---

### Task 5: Add five-minute Quickstart and finish the PR

**Files:**
- Create: `docs/QUICKSTART.md`
- Modify: `README.md`
- Modify: `docs/SETUP.md`
- Modify: `docs/TEST_PROFILES.md`

- [ ] **Step 1: Document the local flow**

```bash
python3 scripts/setup/configure-template.py
python3 scripts/setup/verify-template-config.py --config .template/config.json
python3 scripts/setup/render-setup-summary.py --config .template/config.json
```

Show generated `gh variable set` commands as explicit copy/paste operations, then manual Ruleset/Environment/Secret steps.

- [ ] **Step 2: Define success state**

A repository created from the template reaches a first PR where Quality and `Tests / Required Gate` are green without exposing release secrets.

- [ ] **Step 3: Preserve advanced configuration docs**

Keep direct `MACOS_*` configuration fully documented and link it as the advanced/manual alternative to Quickstart.

- [ ] **Step 4: Run exact-head verification**

Require successful Quality, Tests, Test Infrastructure, and Test Profile Adoption workflows and zero unresolved review threads.

- [ ] **Step 5: Commit docs**

```bash
git add README.md docs/QUICKSTART.md docs/SETUP.md docs/TEST_PROFILES.md
git commit -m "docs: add template setup quickstart"
```
