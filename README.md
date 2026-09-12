# macOS App Development & Release Template

Reusable baseline for developing and distributing macOS applications with GitHub Actions, Developer ID signing, Apple notarization, DMG packaging, and Homebrew Cask distribution.

## Goals

This repository standardizes the parts that should not be redesigned for every macOS application:

- short-lived branch and pull-request workflow
- secret-free CI for untrusted pull requests
- formatter, linter, workflow, shell, and security quality gates
- separation of build jobs from privileged signing/release jobs
- Developer ID signing and Apple notarization
- deterministic DMG packaging and release verification
- GitHub Release and Homebrew Cask hand-off
- least-privilege GitHub Actions permissions and pinned third-party actions

The template intentionally separates **application build logic** from **release credentials**. Application source code is built and tested without release secrets. A privileged release job consumes the resulting unsigned `.app` artifact and performs signing, packaging, notarization, and verification.

## Recommended flow

```text
feat/* / fix/* / refactor/*
          |
          v
     Pull Request
          |
          +-- formatting / lint
          +-- tests / build
          +-- actionlint / zizmor
          +-- ShellCheck / shfmt
          +-- dependency / security checks
          |
          v
        main
          |
          v
       vX.Y.Z tag
          |
          v
 secret-free build job
          |
          v
 unsigned .app artifact
          |
          v
 protected release environment
          |
          +-- import Developer ID certificate
          +-- sign .app
          +-- create and sign DMG
          +-- notarize + staple
          +-- verify signature / ticket / Gatekeeper
          +-- SHA-256
          +-- GitHub Release
          +-- Homebrew Cask update PR
```

## Repository layout

```text
.github/
  CODEOWNERS
  dependabot.yml
  workflows/
    quality.yml
    reusable-homebrew-update.yml
    reusable-macos-release.yml
    reusable-swift-quality.yml
docs/
  BRANCHING.md
  HOMEBREW.md
  QUALITY.md
  RELEASE.md
  SECRETS.md
examples/
  app-release.yml
scripts/
  homebrew/
    render-cask.sh
  release/
    create-dmg.sh
    import-certificate.sh
    notarize.sh
    sign-app.sh
    verify-release.sh
templates/
  homebrew/
    Cask.rb.template
.editorconfig
.swiftformat
.swiftlint.yml
```

## Adoption

1. Create a repository from this template or copy the relevant files into an existing macOS app.
2. Keep application-specific build/test commands in the application repository's secret-free CI job.
3. Upload the unsigned `.app` as a GitHub Actions artifact.
4. Configure a protected `release` GitHub Environment and only place release credentials there.
5. Call `reusable-macos-release.yml` after the build artifact is available.
6. Optionally call `reusable-homebrew-update.yml` after the GitHub Release is published.
7. Configure repository Rulesets according to [`docs/BRANCHING.md`](docs/BRANCHING.md).
8. Configure formatter/linter policy according to [`docs/QUALITY.md`](docs/QUALITY.md).
9. Configure release credentials according to [`docs/SECRETS.md`](docs/SECRETS.md).
10. Use [`examples/app-release.yml`](examples/app-release.yml) as the end-to-end caller example.

Homebrew-specific operation is documented in [`docs/HOMEBREW.md`](docs/HOMEBREW.md).

## Security invariants

The following are design requirements, not recommendations:

- Pull-request CI must complete without Apple signing/notarization secrets.
- Do not execute pull-request-controlled build scripts in a job that has release secrets.
- Do not use `pull_request_target` to check out and execute untrusted pull-request code.
- Default `GITHUB_TOKEN` permissions should be read-only; grant write permissions per job only when required.
- Do not use `secrets: inherit` for privileged reusable workflows. Pass only named secrets.
- Pin third-party GitHub Actions to full commit SHAs and update them through Dependabot.
- A published SemVer tag is immutable; fix a release with a new version instead of moving the tag.

## Policy profiles

### Solo OSS

- PR required for `main`
- zero required approvals (avoids self-approval deadlock)
- all required status checks must pass
- direct push and force push disabled
- squash merge preferred

### Team OSS

- PR required for `main`
- at least one approval
- stale approvals dismissed after relevant changes
- CODEOWNERS review for release/security paths
- all required status checks must pass
- direct push and force push disabled

See the documents in [`docs/`](docs/) for the complete operating model.
