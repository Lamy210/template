# macOS App Development & Release Template

Reusable baseline for developing and distributing macOS applications with GitHub Actions, code-quality gates, Developer ID signing, Apple notarization, DMG packaging, and Homebrew Cask distribution.

## Goals

This repository standardizes the parts that should not be redesigned for every macOS application:

- short-lived branch and pull-request workflow
- explicit coding standards and contribution rules
- secret-free CI for untrusted pull requests
- formatter, linter, complexity, workflow, shell, and security quality gates
- separation of application-source builds from privileged release-control code
- Developer ID signing and Apple notarization
- deterministic DMG packaging and release verification
- immutable GitHub Release and Homebrew Cask hand-off
- least-privilege GitHub Actions permissions and pinned third-party actions

The template deliberately separates **what is released** from **which code is trusted to publish it**. A `vX.Y.Z` tag chooses the application source built without release credentials. A separate `workflow_run` publisher, defined on the current default branch, validates the exact build run/artifact before any Apple secret or repository-write permission is available.

## Recommended flow

```text
feat/* / fix/* / refactor/*
          |
          v
     Pull Request
          |
          +-- SwiftFormat / SwiftLint
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
 Release Build
 tag source; no secrets; read-only
          |
          | exact run-id / attempt artifact
          | unsigned-macos-app.tar.gz
          | build-provenance.json
          v
 Release Publisher / validate
 current default-branch control code
          |
          +-- verify workflow/repository/run/attempt
          +-- verify tag -> SHA and trusted history
          +-- verify artifact/ZIP/tar/app metadata/digests
          +-- re-handoff validator-owned archive + metadata
          |
          v
 protected `release` Environment
          |
          +-- reverify metadata/digest/archive
          +-- import Developer ID certificate
          +-- sign .app and DMG
          +-- notarize + staple
          +-- verify signature / ticket / Gatekeeper
          +-- immutable GitHub Release
          |
          v
 Homebrew Cask update PR
```

The release tag never selects the privileged publisher implementation. This prevents a new tag pointing at an older trusted ancestor from executing stale privileged release logic.

## Repository layout

```text
.github/
  CODEOWNERS
  dependabot.yml
  pull_request_template.md
  workflows/
    quality.yml
    release-isolation-tdd.yml
    swift-quality.yml
    reusable-homebrew-update.yml
    reusable-macos-release.yml
    reusable-swift-quality.yml
docs/
  BRANCHING.md
  CODING_STANDARDS.md
  HOMEBREW.md
  QUALITY.md
  RELEASE.md
  SECRETS.md
  SETUP.md
examples/
  app-release-build.yml
  app-release-publisher.yml
  app-release.yml              # migration pointer only
scripts/
  ci/
  homebrew/
  release/
templates/
  homebrew/
CONTRIBUTING.md
.editorconfig
.swiftformat
.swiftlint.yml
```

## Quality policy

The default Swift profile makes code-quality failures visible as separate concerns:

- **formatting** — SwiftFormat
- **coding-standard/correctness violations** — SwiftLint
- **complexity** — dedicated SwiftLint metrics gate
- **optional semantic analysis** — `swiftlint analyze` when the caller provides a clean compiler log
- **repository automation** — actionlint, zizmor, ShellCheck, and shfmt
- **release trust boundary** — provenance, exact-artifact, source-binding, workflow-contract, and hostile-archive regression tests

The thresholds and exception policy are documented in [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) and [`docs/QUALITY.md`](docs/QUALITY.md). CI uses strict linting, so warning-level quality thresholds are blocking by default.

## Adoption

1. Create a repository from this template or copy the relevant files into an existing macOS app.
2. Apply the one-time GitHub settings in [`docs/SETUP.md`](docs/SETUP.md), including the protected `release` Environment and repository Rulesets.
3. Choose a test policy profile from [`docs/TEST_PROFILES.md`](docs/TEST_PROFILES.md). For example, a SwiftPM project can start with `MACOS_TEST_PROFILE=standard` and `MACOS_TEST_ADAPTER=swiftpm`; a macOS Xcode app can start with `MACOS_TEST_PROFILE=macos-app` and `MACOS_TEST_ADAPTER=xcode`.
4. Configure repository-specific test topology such as working directory, Xcode project/workspace, scheme, plans, destination, and visual manifest. Existing `MACOS_*` policy variables remain supported as the advanced/manual interface and override profile defaults independently.
5. Review [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md) and adapt thresholds only through an intentional policy change.
6. Copy/adapt [`examples/app-release-build.yml`](examples/app-release-build.yml) to `.github/workflows/release-build.yml`. Keep this tag-triggered workflow secret-free and read-only.
7. Copy/adapt [`examples/app-release-publisher.yml`](examples/app-release-publisher.yml) to `.github/workflows/release-publisher.yml` **on the default branch**.
8. Package the unsigned `.app` into the tar archive produced by `scripts/release/package-app-artifact.sh`; do not upload a raw `.app` directory as the release handoff.
9. Keep Apple signing/notarization credentials only in the protected `release` Environment. The called privileged macOS workflow reads them there; the publisher caller does not use `secrets: inherit`.
10. If Homebrew distribution is enabled, pass only the narrow `tap_token` secret to `reusable-homebrew-update.yml` after release publication succeeds.
11. Configure branch/tag policy according to [`docs/BRANCHING.md`](docs/BRANCHING.md) and review credential handling in [`docs/SECRETS.md`](docs/SECRETS.md).
12. Run the test-policy/Test Infrastructure suites and release-isolation contract tests before the first production release.

[`examples/app-release.yml`](examples/app-release.yml) is **migration documentation only**. It intentionally does not contain an executable monolithic release workflow.

Operational details are in [`docs/RELEASE.md`](docs/RELEASE.md), Homebrew-specific operation is in [`docs/HOMEBREW.md`](docs/HOMEBREW.md), and test-profile semantics are in [`docs/TEST_PROFILES.md`](docs/TEST_PROFILES.md).

## Security invariants

The following are design requirements, not recommendations:

- Pull-request CI and the tag-triggered Release Build must complete without Apple signing/notarization secrets.
- The tag build has no repository write permission and never declares `environment: release`.
- A default-branch `workflow_run` publisher independently resolves and validates one exact upstream build run, attempt, source SHA, tag, artifact identity, artifact digest, archive digest, and application identity.
- Untrusted source artifacts are parsed in the secret-free validation job before a validator-owned handoff is created.
- Only the privileged reusable macOS release job declares the protected `release` Environment and receives Apple credentials.
- Privileged publisher control code and entitlements come from the trusted publisher/default-branch checkout, not from the release tag artifact.
- The privileged job revalidates validator-owned metadata and archive content before importing the certificate.
- Do not execute pull-request-controlled or release-artifact-controlled scripts in a job that has release secrets.
- Do not use `pull_request_target` to check out and execute untrusted pull-request code.
- Default `GITHUB_TOKEN` permissions are empty/read-only; grant write permissions only to the smallest job that needs them.
- Do not use `secrets: inherit` at the Apple release boundary; non-Environment credentials such as the Homebrew tap token use narrow named-secret interfaces.
- Pin third-party GitHub Actions to full commit SHAs and update them through Dependabot.
- A published SemVer tag and its release assets are immutable; fix a release with a new version instead of moving/replacing it.

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
