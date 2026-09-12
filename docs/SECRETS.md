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

## Recommended `release` Environment

Create a GitHub Environment named `release` and place all signing/notarization secrets there. Release jobs must explicitly declare:

```yaml
environment: release
```

Where account features permit, add deployment protection/reviewer requirements.

## Suggested secret names

- `MACOS_CERTIFICATE_P12_BASE64`
- `MACOS_CERTIFICATE_PASSWORD`
- `APP_STORE_CONNECT_API_KEY_P8`
- `APP_STORE_CONNECT_KEY_ID`
- `APP_STORE_CONNECT_ISSUER_ID`

Do not use repository-wide secret names such as `PASSWORD`, `KEY`, or `TOKEN` when a narrower name is possible.

## GitHub Actions permissions

Set workflow-level permissions to read-only or empty and grant write permission at the smallest possible job scope.

Example baseline:

```yaml
permissions:
  contents: read
```

Only a release-publishing job should receive `contents: write`. Artifact attestation additionally requires its documented attestation/OIDC permissions.

## Reusable workflows

Privileged reusable workflows must declare named secrets. Do **not** use:

```yaml
secrets: inherit
```

for the release boundary.

Each secret should be passed explicitly so adding a new caller secret cannot silently widen the reusable workflow's credential set.

## Fork pull requests

Pull-request CI must remain useful when the contributor comes from a fork and receives no repository secrets. It should still run format/lint/test/build/security checks.

Never work around fork secret restrictions by giving untrusted pull-request code a privileged execution context.

## `pull_request_target`

Do not use `pull_request_target` to check out and execute contributor-controlled code. If the event is ever required for metadata-only automation, that job must not execute pull-request code or scripts from the pull-request branch.

## Certificate handling

The release scripts create a temporary keychain, import the certificate, use it for signing, then delete the keychain in cleanup. Do not install release certificates into the login keychain on a shared or self-hosted runner.

Prefer ephemeral GitHub-hosted macOS runners for the privileged release job unless a self-hosted runner has been intentionally hardened for signing.

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
2. the release workflow obtains a short-lived installation token
3. only the Homebrew update job receives that token

A fine-grained PAT may be used as a temporary fallback, but should be scoped only to the tap repository and required permissions.

## Secret scanning

For public repositories enable:

- GitHub secret scanning
- push protection
- dependency review
- CodeQL/default code scanning where supported

If a real credential is committed, deleting the line is not sufficient. Revoke/rotate the credential first, then clean history only when necessary.
