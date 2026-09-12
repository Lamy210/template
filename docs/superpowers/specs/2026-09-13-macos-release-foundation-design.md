# macOS Release Foundation Design

Date: 2026-09-13
Status: Draft for review

## 1. Purpose

This repository defines a reusable baseline for macOS application development and distribution. It standardizes branch policy, code quality, GitHub Actions security, Developer ID signing, Apple notarization, DMG packaging, GitHub Releases, and Homebrew Cask hand-off without coupling the release layer to a particular application build system.

The primary adoption model for Phase 1 is a **template/copy model**: create an application repository from this template, or copy the relevant files into an existing application repository. Application-specific build logic remains in the application repository.

A centrally hosted cross-repository reusable-workflow model is explicitly deferred to Phase 2. GitHub reusable workflows execute actions in the caller context; in particular, `actions/checkout` checks out the caller repository. The current release workflows call repository-local `scripts/release/*`, so exposing them as remote central workflows without packaging those scripts separately would be incorrect.

## 2. Goals

- Keep pull-request CI completely independent of release credentials.
- Keep `main` continuously releasable through short-lived branches and required quality gates.
- Make formatter, linter, workflow, shell, dependency, and security checks reproducible.
- Ensure release credentials are only available in a protected release job.
- Separate application build/test from signing/notarization.
- Produce a signed, notarized, stapled, verified DMG with a SHA-256 checksum.
- Publish a GitHub Release only after release verification succeeds.
- Automate a Homebrew Cask update through a separate pull request.
- Keep GitHub Actions permissions least-privilege and pin third-party actions to immutable commit SHAs.
- Make the template usable by solo OSS projects now and team projects later.

## 3. Non-goals for Phase 1

- Building every supported application framework inside the release workflow.
- Central cross-repository execution of `scripts/release/*` from this repository.
- Automatic merging of Homebrew Cask changes.
- Supporting the Mac App Store distribution path.
- Supporting installer `.pkg` output.
- Automatically signing arbitrary nested code without application-specific knowledge.
- Hiding application-specific entitlements or build settings inside the template.

## 4. Architectural decisions

### 4.1 Adoption model

Phase 1 uses the repository as a GitHub Template Repository or a source of files to copy into an existing application repository.

This guarantees that:

- reusable workflows and `scripts/release/*` live in the same application repository;
- relative script paths resolve predictably;
- application-specific entitlements and build scripts remain local;
- release behavior can be reviewed together with application code.

Phase 2 may add a central reusable release service after the release helpers are packaged as versioned remote composite actions or another immutable distribution unit.

### 4.2 Trust boundary

The critical boundary is between **building untrusted application code** and **using release credentials**.

```text
source/tag
   |
   v
secret-free build/test job
   |
   v
unsigned .app artifact
   |
   +---- no Apple credentials above this line ----+
   |
   v
protected release job
   |
   +-- import Developer ID certificate
   +-- validate bundle metadata
   +-- sign application
   +-- create/sign DMG
   +-- notarize/staple
   +-- verify
   +-- checksum
   +-- publish
```

Release jobs must not execute an arbitrary build command supplied by a pull request. They consume an artifact from the secret-free build job in the same trusted tag workflow.

### 4.3 Application signing

The generic signing helper signs the root application bundle and intentionally does not use `codesign --deep` for signing.

Applications containing frameworks, XPC services, helpers, extensions, login items, or other nested code must provide an application-specific inside-out signing adapter before the root bundle is signed. Verification may use `--deep` to detect invalid nested signatures, but signing must remain explicit.

### 4.4 DMG packaging

The default DMG implementation uses Apple-provided `hdiutil` and a minimal layout:

- application bundle;
- `/Applications` symlink;
- compressed UDZO image.

Styled DMGs are optional future adapters. The minimal path is the default because it reduces dependencies and release failure modes.

### 4.5 Homebrew

GUI applications are distributed through Homebrew Cask, not Formula.

The application release publishes the DMG and checksum first. A subsequent Homebrew job obtains the checksum, renders the Cask, pushes an automation branch to the tap repository, and opens or reuses a pull request. Tap CI must pass before merge.

## 5. Branch and merge policy

The default model is trunk-based development:

- `main`: protected and continuously releasable;
- `feat/*`: short-lived feature work;
- `fix/*`: bug fixes;
- `refactor/*`: refactoring;
- `perf/*`: performance work;
- `security/*`: security fixes;
- `docs/*`: documentation;
- `chore/*`: maintenance/CI/dependency work.

Long-lived `develop` is not part of the standard model.

Preferred merge method is squash merge. Direct pushes, force pushes, and branch deletion on `main` should be blocked by repository Rulesets.

### Solo OSS profile

- pull request required;
- required approvals: 0;
- required status checks must pass;
- conversations resolved before merge;
- direct push/force push disabled.

### Team OSS profile

Adds:

- at least one approval;
- stale approval dismissal;
- CODEOWNERS review for security/release-sensitive paths.

Stable release tags use `vX.Y.Z` SemVer and are immutable after publication.

## 6. Quality model

Quality is layered rather than represented by a single linter.

### Repository/workflow quality

- EditorConfig for basic text normalization;
- `actionlint` for GitHub Actions semantics;
- `zizmor` for GitHub Actions security analysis;
- ShellCheck for shell correctness;
- `shfmt` for shell formatting;
- Dependabot for dependency/update visibility;
- pinned GitHub Actions commit SHAs.

### Swift application profile

- SwiftFormat for deterministic formatting;
- SwiftLint for static style/maintainability rules;
- build/compiler warnings;
- unit tests;
- project-specific integration tests.

Coverage policy should use a ratchet/baseline model for existing repositories instead of a universal fixed threshold. New projects should start with a clean warning/lint baseline.

## 7. CI model

### Pull request

Must be secret-free. It may run formatting, linting, tests, builds, workflow analysis, dependency review, and code scanning.

`pull_request_target` must not be used to check out and execute untrusted pull-request code.

### Main

Runs the same required quality checks. Merging into `main` does not itself unlock Apple credentials.

### Release tag

A stable `vX.Y.Z` tag triggers a secret-free release build. The unsigned `.app` is uploaded as an Actions artifact. The privileged release job depends on that build and consumes the artifact from the same workflow run.

The release job uses a protected `release` GitHub Environment. Default workflow permissions are read-only; write permissions are granted only to jobs that require them.

## 8. Secrets and credential handling

Release credentials include:

- Developer ID Application certificate encoded as PKCS#12/base64;
- PKCS#12 password;
- App Store Connect Team API private key;
- API key ID;
- issuer ID;
- Homebrew tap write credential when a separate tap repository is used.

Requirements:

- no release secret in pull-request jobs;
- no `secrets: inherit` for privileged jobs;
- explicit named secret mapping only;
- temporary keychain for certificate import;
- temporary private-key files with restrictive permissions;
- cleanup via `always()`/shell traps;
- Homebrew write token should be short-lived GitHub App installation credentials when practical; a fine-grained PAT is fallback only.

GitHub Environment semantics must be documented carefully: environment secrets are not passed through `workflow_call` like ordinary caller secrets, and an environment defined at the reusable job can affect secret resolution. The Phase 1 copy model avoids cross-repository ambiguity because caller and reusable workflow reside in the same application repository.

## 9. Release validation gates

Before publication, the workflow must validate:

- stable tag format;
- safe relative application path;
- expected bundle identifier;
- `CFBundleShortVersionString` equals the tag version;
- Developer ID signature validity;
- Hardened Runtime through signing options;
- nested signature validity where applicable;
- DMG integrity;
- DMG signature validity;
- notarization result is `Accepted`;
- stapled ticket validates;
- Gatekeeper assessment passes;
- SHA-256 checksum is generated after final stapling;
- GitHub Release is created/updated only after all previous gates succeed.

## 10. Failure modes and recovery

### Build failure

No privileged job starts. Fix source/build configuration and create a new successful workflow run.

### Signing failure

Do not publish. Verify certificate validity, signing identity, nested code signatures, entitlements, and keychain import.

### Notarization failure

Do not publish. Inspect Apple notarization output/logs, fix the application, and create a new release version when the tag has already been published externally.

### GitHub Release failure after successful notarization

The signed artifact remains in workflow artifacts for the configured retention window. Retry publication only if the workflow inputs and tag still identify the same verified artifact.

### Homebrew update failure

The application release remains valid. Retry only the Homebrew hand-off after fixing tap credentials or Cask validation.

### Credential compromise

Revoke/rotate the compromised credential first. Repository history cleanup is secondary and does not replace rotation.

## 11. Observability

CI should expose enough non-secret evidence to diagnose failures:

- workflow/job/step result;
- tag/version and expected bundle ID;
- signing verification output without private material;
- notarization submission ID and status;
- DMG verification result;
- checksum;
- Homebrew PR URL.

Never print private keys, certificate passwords, raw PKCS#12 data, or bearer tokens.

## 12. Security invariants

These are hard requirements:

1. PR CI succeeds without release secrets.
2. Privileged jobs never execute PR-controlled build commands.
3. Third-party Actions are pinned to full commit SHAs.
4. `GITHUB_TOKEN` is read-only by default.
5. Stable published tags are not moved.
6. Release publication follows signing, notarization, and verification; never precedes them.
7. Cross-repository write credentials are scoped only to the tap operation.
8. Secrets are explicitly named rather than inherited wholesale.
9. Nested application code is not blindly signed with `--deep`.
10. The template must document when application-specific adapters are required.

## 13. Test strategy

The repository needs tests at three levels.

### Static CI tests

- `actionlint` for every workflow;
- `zizmor` for workflow security;
- ShellCheck and `shfmt` for shell helpers.

### Script behavior tests

Portable logic such as path validation and Cask rendering should have automated tests that run on Linux where possible. macOS-only helpers should separate portable validation from platform commands so validation can be tested without a Developer ID certificate.

### Integration smoke tests

A dedicated test fixture/application should eventually verify the non-secret part of the release path on macOS. Real signing/notarization smoke tests require controlled Apple credentials and should run manually or on a low-frequency protected schedule, not on every PR.

## 14. Phase 1 completion criteria

Phase 1 is complete when:

- repository Quality workflow is green;
- branch/quality/secrets/release/Homebrew documentation is internally consistent;
- example caller workflow matches actual reusable workflow inputs/secrets;
- release scripts pass ShellCheck/shfmt;
- release workflow cannot run from non-stable tags;
- application metadata is validated before signing;
- checksum is produced after final notarization/stapling;
- Homebrew update uses a separate PR;
- no release secrets are needed by PR CI;
- the template clearly states that Phase 1 is copy/template based.

## 15. Phase 2 direction

Phase 2 may provide centrally managed reusable workflows so fixes in this repository can propagate without copying files into every application repository.

Before enabling that model, repository-local release scripts must be converted into versioned remotely consumable units, for example remote composite actions. Every consuming application must pin the central release kit to an immutable release tag or commit SHA. Cross-repository reusable workflow behavior, checkout context, environment protection, permissions, and secret resolution must receive dedicated integration tests before central mode is advertised as supported.
