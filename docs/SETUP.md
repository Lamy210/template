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

## 9. Required status checks

After the first pull request runs successfully, select stable check names from GitHub's Ruleset UI. Do not type a guessed check name before it has run at least once.

For this template itself, require at minimum the jobs produced by:

```text
Quality / Repository hygiene
Quality / GitHub Actions security
Swift Quality / Swift quality
```

The exact UI label can vary with GitHub's workflow/job presentation; select the observed checks from a successful pull request.

Application repositories should additionally require their application build and unit/integration test jobs. If an application does not use Swift, remove or replace the Swift profile rather than keeping a permanently skipped/irrelevant required check.

The Swift quality job includes:

- SwiftFormat drift detection
- a dedicated complexity gate
- the full SwiftLint coding-standard/correctness pass
- optional SwiftLint analyzer rules when a clean compiler log is provided

Avoid renaming required workflow/job names casually because Rulesets refer to the resulting status-check names.

## 10. Coding and complexity policy

Review these files before the first application PR:

- `docs/CODING_STANDARDS.md`
- `docs/QUALITY.md`
- `.swiftformat`
- `.swiftlint.yml`

The default complexity limits are intentionally moderate and CI runs SwiftLint with `--strict`, so warning thresholds are blocking. Do not raise thresholds merely to get the first feature merged. For an existing codebase with known debt, define an explicit baseline/ratchet migration instead.

## 11. Template repository setting

For the central reusable starter repository, enable GitHub's **Template repository** setting. New applications can then be created from the template while keeping their own independent history.

After creating a project from the template, replace project-specific placeholders and review/remove files that do not apply to that application.

## 12. First-release verification

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
