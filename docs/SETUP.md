# One-time GitHub Repository Setup

The files in this template do not automatically create repository Rulesets, Environments, or Secrets. Apply the following settings after creating a repository from the template.

## 1. Repository merge policy

Recommended for the default `main` branch:

- enable squash merge
- disable merge commits unless the project explicitly needs them
- optionally disable rebase merge to keep one consistent merge strategy
- enable automatic deletion of merged feature branches when appropriate

The intended history model is one squash commit per pull request.

## 2. `main` Ruleset — Solo OSS profile

Create a branch Ruleset targeting `main` with:

- restrict deletion
- block force pushes
- require a pull request before merging
- required approvals: `0`
- require conversation resolution
- require linear history
- require the branch to be up to date before merging
- require the template's quality status checks
- keep bypass actors to the minimum necessary for repository recovery

Do not configure one required approval for a repository with only one maintainer; it creates a self-approval deadlock.

## 3. `main` Ruleset — Team OSS profile

When multiple maintainers exist, change the pull-request policy to:

- required approvals: at least `1`
- dismiss stale approvals when relevant code changes
- require CODEOWNERS review for sensitive paths

Keep all other protections from the Solo profile.

## 4. Release tag Ruleset

Create a tag Ruleset targeting:

```text
v*
```

Recommended policy:

- restrict deletion
- restrict updates
- limit creation to maintainers/release automation

A published tag must be immutable. A bad `v1.2.0` release is fixed by `v1.2.1`, not by moving `v1.2.0`.

## 5. Protected `release` Environment

Create a GitHub Environment named exactly:

```text
release
```

The reusable macOS release workflow references this name. This Environment is part of the privileged release trust boundary, so its deployment-ref restriction is required rather than optional.

Configure **Deployment branches and tags** using **Selected branches and tags** and allow only the repository's default branch (normally `main`) as a **Branch** rule. Do not add a `v*` tag rule to this Environment: `workflow_run` publishers execute with `GITHUB_REF` set to the default branch, and the called reusable workflow inherits the caller's ref. The release tag is independently validated as release input; it is not the deployment ref that enters this Environment.

Do not leave the `release` Environment unrestricted. A feature branch, pull-request ref, or arbitrary tag must not be able to enter the privileged Environment merely by calling the reusable release workflow.

Where the repository has an independent release reviewer, required-reviewer protection can be added as defense in depth. Do not create a one-person approval deadlock for a solo-maintainer repository. If the account/plan supports disabling administrator bypass for Environment protections and operational recovery does not require it, prefer disabling that bypass.

Keep privileged release secrets in this Environment rather than exposing them to ordinary PR jobs.

After configuring the Environment, run the read-only doctor:

```bash
bash scripts/release/audit-release-environment.sh owner/repo
```

The doctor verifies that the Environment is named `release`, uses custom deployment branch policies rather than unrestricted/protected-branches mode, and has exactly one deployment policy whose name equals the repository default branch. It uses only read endpoints and does not modify Environment settings.

GitHub's deployment-branch-policy list response does not always expose whether a returned policy was originally created as a branch or tag policy. When a `type` field is present the doctor requires `branch`; when GitHub omits it, the doctor cannot prove branch-vs-tag identity from REST output alone. Therefore the first-release runtime policy proof below remains mandatory: the default branch must be able to enter the `release` Environment while a feature/temporary branch and arbitrary tag must not.

For the runtime policy proof, use a **disposable repository** with the same `release` Environment policy. Copy the inert example workflow onto that disposable repository's default branch:

```bash
mkdir -p .github/workflows
cp examples/release-environment-proof.yml \
  .github/workflows/release-environment-proof.yml
```

Commit/push that workflow in the disposable repository, then run:

```bash
bash scripts/release/prove-release-environment-policy.sh \
  --repository owner/disposable-release-proof \
  --confirm-disposable owner/disposable-release-proof
```

The proof first dispatches the secret-free workflow from the default branch and requires the `release` Environment job to succeed. It then creates a temporary branch and arbitrary tag at the same commit and requires those two Environment jobs to be denied while their non-Environment baseline jobs still succeed. This positive control prevents an accidentally deny-all Environment from producing a false pass. Temporary refs are removed afterward. The script refuses the current `GITHUB_REPOSITORY`, so do not weaken that guardrail to test the production repository.

## 6. Release secrets

Add the following secrets to the `release` Environment:

```text
MACOS_CERTIFICATE_P12_BASE64
MACOS_CERTIFICATE_PASSWORD
APP_STORE_CONNECT_API_KEY_P8
APP_STORE_CONNECT_KEY_ID
APP_STORE_CONNECT_ISSUER_ID
```

The reusable release job reads these names directly after entering the protected `release` Environment. Do not duplicate them as repository-level secrets and do not attempt to pass them through `workflow_call`.

Do not add Apple release credentials to workflows triggered by untrusted pull requests.

## 7. Homebrew tap credential

If Homebrew publishing is enabled, add a separate credential such as:

```text
HOMEBREW_TAP_TOKEN
```

Preferred implementation: a short-lived GitHub App installation token limited to the tap repository. A fine-grained PAT is an acceptable temporary fallback when narrowly scoped.

Do not reuse Apple credentials for Homebrew access.

## 8. Security features

For a public OSS repository, enable where available:

- Dependabot alerts
- Dependabot security updates
- secret scanning
- push protection
- dependency graph / dependency review
- CodeQL default setup when the application's language/build model is supported

The repository-level `quality.yml` covers GitHub Actions security with `zizmor` and workflow/shell correctness with `actionlint`, ShellCheck, and shfmt. The `swift-quality.yml` workflow enforces Swift formatting, coding standards, and complexity limits.

## 9. Test policy profile variables

For a new adopter, prefer the named profile interface documented in [`TEST_PROFILES.md`](TEST_PROFILES.md). Configure repository variables rather than secrets.

SwiftPM baseline:

```text
MACOS_TEST_PROFILE=standard
MACOS_TEST_ADAPTER=swiftpm
```

Xcode macOS application baseline:

```text
MACOS_TEST_PROFILE=macos-app
MACOS_TEST_ADAPTER=xcode
MACOS_TEST_WORKING_DIRECTORY=.
MACOS_TEST_PROJECT_PATH=MyApp.xcodeproj
MACOS_TEST_SCHEME=MyApp
```

Use `MACOS_TEST_WORKSPACE_PATH` instead of `MACOS_TEST_PROJECT_PATH` when the application builds from a workspace. Configure only repository-specific values that apply; do not invent placeholder paths merely to satisfy the workflow.

The four supported profiles are `minimal`, `standard`, `macos-app`, and `macos-ui-strict`. `macos-app` and `macos-ui-strict` require the Xcode adapter.

Existing low-level policy variables remain supported:

```text
MACOS_INTEGRATION_ENABLED
MACOS_INTEGRATION_REQUIRED
MACOS_COVERAGE_ENABLED
MACOS_COVERAGE_REQUIRED
MACOS_E2E_ENABLED
MACOS_E2E_REQUIRED
MACOS_VISUAL_ENABLED
MACOS_VISUAL_REQUIRED
MACOS_VISUAL_BOOTSTRAP
```

They override profile defaults independently. An override never silently weakens another field. For example, setting only `MACOS_E2E_ENABLED=false` under `macos-app` remains invalid because that profile still requires E2E; set both enabled and required to false when intentionally disabling the subsystem.

Leave `MACOS_TEST_PROFILE` empty to retain the legacy low-level behavior exactly. Boolean policy variables accept only empty, `true`, or `false`; malformed values fail closed.

## 10. Required status checks

After the first pull request runs successfully, select stable check names from GitHub's Ruleset UI. Do not type a guessed check name before it has run at least once.

For this template itself, require the stable aggregate checks observed from a successful pull request:

```text
Required gate
Tests / Required Gate
swift-quality / Swift quality
```

Do not infer these names from YAML alone. Confirm the exact Check Runs emitted by GitHub after the testing and release/governance foundations have landed, then select those observed checks in the Ruleset UI.

Application repositories should additionally require their application build and unit/integration test jobs. If an application does not use Swift, remove or replace the Swift profile rather than keeping a permanently skipped/irrelevant required check.

The Swift quality job includes:

- SwiftFormat drift detection
- a dedicated complexity gate
- the full SwiftLint coding-standard/correctness pass
- optional SwiftLint analyzer rules when a clean compiler log is provided

Avoid renaming required workflow/job names casually because Rulesets refer to the resulting status-check names.

## 11. Coding and complexity policy

Review these files before the first application PR:

- `docs/CODING_STANDARDS.md`
- `docs/QUALITY.md`
- `.swiftformat`
- `.swiftlint.yml`

The default complexity limits are intentionally moderate and CI runs SwiftLint with `--strict`, so warning thresholds are blocking. Do not raise thresholds merely to get the first feature merged. For an existing codebase with known debt, define an explicit baseline/ratchet migration instead.

## 12. Template repository setting

For the central reusable starter repository, enable GitHub's **Template repository** setting. New applications can then be created from the template while keeping their own independent history.

After creating a project from the template, replace project-specific placeholders and review/remove files that do not apply to that application.

## 13. First-release verification

Before the first production release, run a controlled test release and verify all of the following end to end:

- unsigned application artifact is produced without release secrets
- release job can access the `release` Environment only from the intended default-branch publisher path
- a feature branch or pull-request ref cannot enter the `release` Environment
- Developer ID certificate imports into the temporary keychain
- app signature validates
- DMG builds and validates
- Apple notarization reaches `Accepted`
- stapling succeeds
- Gatekeeper assessment succeeds
- checksum asset is published
- Homebrew tap PR is generated with the expected version and SHA-256

Do not treat the first real user-facing release as the integration test for signing credentials or the Homebrew path.
