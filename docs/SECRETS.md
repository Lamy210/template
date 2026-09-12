# Secrets and Privileged CI

## Threat model

Release credentials are more sensitive than ordinary CI configuration. A malicious or accidentally modified build script must not gain access to Developer ID certificates, App Store Connect private keys, or cross-repository write credentials.

The core rule is:

> Build untrusted/application-controlled code without release secrets. Only pass the resulting artifact into the privileged signing/release stage.

## Secret classes

### Public configuration

Safe to commit:

- app name
- bundle identifier
- minimum supported macOS version
- Homebrew Cask token
- release channel names

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

Create a GitHub Environment named exactly `release` and place all Apple signing/notarization secrets there. The reusable macOS release workflow declares:

```yaml
environment: release
```

The release job therefore receives these secrets from that Environment only after the Environment's protection rules are satisfied.

Where account features permit, add deployment protection/reviewer requirements and restrict which protected tags may deploy to the Environment.

## Required Apple secret names

The reusable release workflow reads the following names directly from the `release` Environment:

- `MACOS_CERTIFICATE_P12_BASE64`
- `MACOS_CERTIFICATE_PASSWORD`
- `APP_STORE_CONNECT_API_KEY_P8`
- `APP_STORE_CONNECT_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`

Do not also create repository-level copies of these Apple release credentials. Keeping one protected source avoids accidentally making the credentials available to ordinary repository jobs.

Do not use broad names such as `PASSWORD`, `KEY`, or `TOKEN` when a narrower name is possible.

## GitHub Actions permissions

Set workflow-level permissions to read-only or empty and grant write permission at the smallest possible job scope.

Example baseline:

```yaml
permissions:
  contents: read
```

Only a release-publishing job should receive `contents: write`. Artifact attestation additionally requires its documented attestation/OIDC permissions.

## Reusable workflow and Environment caveat

GitHub does not allow Environment secrets to be passed from a caller via `on.workflow_call`. If the called workflow declares an Environment at job level, that Environment's secrets are used instead of same-named caller-passed secrets.

For that reason this template deliberately does **not** pass Apple credentials through the reusable workflow's `secrets:` interface. The privileged job references the fixed Environment secret names directly.

Do not work around this by moving the Apple keys to repository secrets or by using `secrets: inherit`.

A different reusable workflow that handles non-Environment credentials, such as the Homebrew tap updater, may use a narrow named-secret interface because it is a separate privilege domain.

## Fork pull requests

Pull-request CI must remain useful when the contributor comes from a fork and receives no repository secrets. It should still run format/lint/test/build/security checks.

Never work around fork secret restrictions by giving untrusted pull-request code a privileged execution context.

## `pull_request_target`

Do not use `pull_request_target` to check out and execute contributor-controlled code. If the event is ever required for metadata-only automation, that job must not execute pull-request code or scripts from the pull-request branch.

## Certificate handling

The release scripts create a temporary keychain, import the certificate, use it for signing, then delete the keychain in cleanup. Do not install release certificates into the login keychain on a shared or self-hosted runner.

Prefer ephemeral GitHub-hosted macOS runners for the privileged release job unless a self-hosted runner has been intentionally hardened for signing.

## Release-script trust

The privileged release job executes the repository's shared release scripts, so changes to these paths are security-sensitive:

```text
.github/workflows/reusable-macos-release.yml
scripts/release/**
*.entitlements
```

Protect them through PR-only changes and CODEOWNERS review in multi-maintainer repositories. A contributor-controlled PR must never be able to modify and execute these files with release credentials before the change is reviewed and merged into the trusted release ref.

## Log safety

- never enable shell tracing (`set -x`) in secret-handling scripts
- never echo private key/certificate contents
- mask dynamically derived credentials with GitHub's masking command when applicable
- avoid passing secrets on command lines when a tool supports files or environment variables
- remove temporary key/keychain files in an `always()` cleanup step

## Cross-repository Homebrew writes

The repository-scoped `GITHUB_TOKEN` must not be treated as a general cross-repository credential.

Preferred design:

1. a GitHub App has minimal write permission to the Homebrew tap repository
2. the Homebrew update workflow obtains a short-lived installation token
3. only the Homebrew update job receives that token

A fine-grained PAT may be used as a temporary fallback, but should be scoped only to the tap repository and required permissions.

## Secret scanning

For public repositories enable:

- GitHub secret scanning
- push protection
- dependency review
- CodeQL/default code scanning where supported

If a real credential is committed, deleting the line is not sufficient. Revoke/rotate the credential first, then clean history only when necessary.
