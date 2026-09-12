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

The reusable macOS release workflow references this name.

Where supported and useful, configure environment protection such as required reviewers and deployment tag restrictions. Keep privileged release secrets in this Environment rather than exposing them to ordinary PR jobs.

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

The repository-level `quality.yml` already covers GitHub Actions security with `zizmor` and workflow/shell correctness with `actionlint`, ShellCheck, and shfmt.

## 9. Required status checks

After the first pull request runs successfully, select the stable checks from the `Quality` workflow as required checks in the `main` Ruleset.

At minimum require:

```text
Repository hygiene
GitHub Actions security
```

Application repositories should additionally require their build, unit-test, integration-test, and Swift quality jobs.

Avoid renaming required job names casually because Rulesets refer to the resulting status-check names.

## 10. Template repository setting

For the central reusable starter repository, enable GitHub's **Template repository** setting. New applications can then be created from the template while keeping their own independent history.

After creating a project from the template, replace project-specific placeholders and review/remove files that do not apply to that application.

## 11. First-release verification

Before the first production release, run a controlled test release and verify all of the following end to end:

- unsigned application artifact is produced without release secrets
- release job can access the `release` Environment only on the intended tag path
- Developer ID certificate imports into the temporary keychain
- app signature validates
- DMG builds and validates
- Apple notarization reaches `Accepted`
- stapling succeeds
- Gatekeeper assessment succeeds
- checksum asset is published
- Homebrew tap PR is generated with the expected version and SHA-256

Do not treat the first real user-facing release as the integration test for signing credentials or the Homebrew path.
