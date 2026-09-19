# Secrets and Privileged CI

## Threat model

Release credentials are more sensitive than ordinary CI configuration. A malicious or accidentally modified build script, old release-tag commit, downloaded artifact, or pull-request change must not gain access to Developer ID certificates, App Store Connect private keys, or cross-repository write credentials.

The core rule is:

> Build application-controlled source without release secrets. Validate its exact provenance and artifact identity in a separate secret-free publisher job. Only the trusted default-branch publisher may enter the protected release Environment.

## Three release trust zones

### 1. Tag-triggered Release Build

The release build runs from the `vX.Y.Z` application source commit.

It must have:

- no Apple secrets;
- no Homebrew tap token;
- no `release` Environment;
- no repository write permission;
- no call to the privileged reusable macOS release workflow.

Its only release output is an unsigned application archive plus strict provenance, uploaded under an artifact name bound to the exact run ID and attempt.

### 2. Default-branch publisher validation

`release-publisher.yml` is a `workflow_run` workflow that must exist on the repository default branch. Its validation job uses current trusted publisher code rather than the release-tag commit.

The validation job has only:

```yaml
permissions:
  actions: read
  contents: read
```

It has no Environment and no secrets. It resolves one exact upstream workflow run/artifact, validates provenance/tag/source/history/digests/archive/app metadata, and creates a new validator-owned handoff artifact inside the publisher run.

### 3. Privileged signing/publication

Only the called `reusable-macos-release.yml` job declares:

```yaml
environment: release
permissions:
  contents: write
```

It revalidates the validator-owned metadata and archive before importing a certificate. Apple credentials are read directly from the fixed protected Environment.

The publisher caller deliberately does **not** use `secrets: inherit` and does not map Apple secrets through `workflow_call`.

## Secret classes

### Public configuration

Safe to commit:

- app name
- bundle identifier
- minimum supported macOS version
- Homebrew Cask token
- release channel names
- expected upstream workflow path

### Sensitive but non-secret configuration

Prefer GitHub Actions variables when appropriate:

- Apple Team ID
- App Store Connect issuer/key identifiers when policy permits
- Homebrew tap repository name

Treat these as metadata, not authentication material.

### Secrets

Store only in GitHub Secrets / protected Environments:

- Developer ID Application certificate (`.p12`, normally base64 encoded for CI transport)
- certificate password
- App Store Connect API private key (`.p8`)
- credentials capable of writing to another repository

## Required `release` Environment

Create a GitHub Environment named exactly `release` and place all Apple signing/notarization secrets there. The reusable macOS release workflow declares `environment: release`; no upstream tag-build or publisher-validation job does.

Where account features permit, add deployment protection/reviewer requirements and restrict deployments to the intended release policy. Environment protection is an additional control, not a replacement for publisher provenance validation.

## Required Apple secret names

The reusable release workflow reads the following names directly from the `release` Environment:

- `MACOS_CERTIFICATE_P12_BASE64`
- `MACOS_CERTIFICATE_PASSWORD`
- `APP_STORE_CONNECT_API_KEY_P8`
- `APP_STORE_CONNECT_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`

Do not also create repository-level copies of these Apple release credentials. Keeping one protected source avoids accidentally making them available to ordinary repository jobs.

Do not use broad names such as `PASSWORD`, `KEY`, or `TOKEN` when a narrower name is possible.

## Why the caller does not pass Apple secrets

GitHub reusable workflows can use an Environment declared in the called job. This template uses that boundary intentionally.

The publisher calls the privileged reusable workflow with validated non-secret inputs only. It does not use:

```yaml
secrets: inherit
```

and it does not map Apple secret names explicitly.

The Apple secrets are resolved only when the called job enters `environment: release`. This keeps unrelated repository/organization secrets out of the privileged workflow interface and prevents the secret-free validation job from gaining access to them.

## GitHub Actions permissions

Use `permissions: {}` or read-only workflow defaults and grant capabilities at the smallest possible job scope.

Expected release permissions are:

- Release Build: `contents: read`
- Publisher validation: `actions: read`, `contents: read`
- Privileged signing/publication: `contents: write`
- Homebrew updater: source repository read access plus one narrow named tap credential

Do not grant release write permission to the tag build or validation job.

## Fork pull requests

Pull-request CI must remain useful when the contributor comes from a fork and receives no repository secrets. It should still run format/lint/test/build/security checks.

Never work around fork secret restrictions by giving untrusted pull-request code a privileged execution context.

## `pull_request_target`

Do not use `pull_request_target` to check out and execute contributor-controlled code. If the event is ever required for metadata-only automation, that job must not execute pull-request code or scripts from the pull-request branch.

## Artifact input is not trusted because CI produced it

The privileged publisher treats the upstream build artifact as untrusted input even when the upstream workflow succeeded.

Before release secrets are available, validate:

- exact source repository/workflow/run/attempt;
- exact artifact ID/name/digest;
- Actions Artifact ZIP confinement;
- build provenance;
- stable tag and source SHA binding;
- source reachability from trusted default-branch history;
- tar archive digest and confinement;
- application bundle ID/version/executable contract.

The secret-free validator then re-handoffs only the validated archive plus validator-owned metadata. The privileged job rechecks both before certificate import.

## Certificate handling

The release scripts create a temporary keychain, import the certificate, use it for signing, then delete the keychain in an `always()` cleanup step. Do not install release certificates into the login keychain on a shared or self-hosted runner.

Prefer ephemeral GitHub-hosted macOS runners unless a self-hosted signing runner has been intentionally hardened.

## Release-control code trust

The privileged release job executes control code from the current default-branch publisher checkout. Changes to these paths are security-sensitive:

```text
.github/workflows/reusable-macos-release.yml
examples/app-release-publisher.yml
scripts/release/**
*.entitlements
```

The tag commit may select application source, but it must not select the privileged publisher implementation. Do not reintroduce a same-tag-context call to `./.github/workflows/reusable-macos-release.yml`.

Entitlements used by the privileged job should come from the trusted publisher/default-branch checkout, not from the downloaded release artifact.

## Log safety

- never enable shell tracing (`set -x`) in secret-handling scripts
- never echo private key/certificate contents
- mask dynamically derived credentials when applicable
- avoid passing secrets on command lines when a tool supports files or environment variables
- remove temporary key/keychain files in an `always()` cleanup step
- do not expand potentially attacker-controlled workflow values directly into shell source; bind them through step `env:` and quote shell variables

## Cross-repository Homebrew writes

Homebrew is a separate privilege domain. `reusable-homebrew-update.yml` accepts only the narrow named secret `tap_token` and receives the already-validated `source_tag` as a non-secret input after signing/publication succeeds.

Preferred credential:

1. a GitHub App with minimal permission to the tap repository;
2. a short-lived installation token;
3. access only to the Homebrew update job.

A fine-grained PAT is a temporary fallback and should be scoped only to the tap repository and required permissions.

Do not use `secrets: inherit` for Homebrew either.

## Secret scanning

For public repositories enable:

- GitHub secret scanning
- push protection
- dependency review
- CodeQL/default code scanning where supported

If a real credential is committed, deleting the line is not sufficient. Revoke/rotate the credential first, then clean history only when necessary.
