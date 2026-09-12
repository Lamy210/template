# macOS Release Pipeline

## Design principle

The release pipeline is split into two trust zones.

### Zone A: secret-free build

The application repository builds and tests the app without release credentials. The output is an **unsigned `.app` artifact**.

### Zone B: privileged release

A protected macOS release job downloads only that artifact and performs:

1. temporary keychain creation
2. Developer ID certificate import
3. app signing
4. signature verification
5. DMG creation
6. DMG signing
7. Apple notarization
8. ticket stapling
9. Gatekeeper/signature validation
10. SHA-256 generation
11. GitHub Release publication
12. optional Homebrew Cask update

The privileged job must not execute arbitrary build/test commands supplied by the application repository.

## Caller workflow pattern

When this repository is used as a template, the application repository contains the reusable workflows and release scripts locally. A typical release job is:

```yaml
jobs:
  build:
    runs-on: macos-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<full-commit-sha>
        with:
          persist-credentials: false
      - name: Build and test
        run: ./scripts/ci/build-release-artifact.sh
      - uses: actions/upload-artifact@<full-commit-sha>
        with:
          name: unsigned-macos-app
          path: build/MyApp.app

  release:
    needs: build
    permissions:
      contents: write
    uses: ./.github/workflows/reusable-macos-release.yml
    with:
      artifact_name: unsigned-macos-app
      app_name: MyApp
      app_path: MyApp.app
      bundle_id: com.example.MyApp
      dmg_name: MyApp-${{ github.ref_name }}.dmg
      signing_identity: "Developer ID Application: Example Developer (TEAMID1234)"
      entitlements_path: MyApp/MyApp.entitlements
```

See `examples/app-release.yml` for an end-to-end build → signed release → Homebrew update example.

The called workflow's privileged job declares `environment: release` and reads Apple credentials directly from that protected Environment. GitHub does not support passing Environment secrets through `on.workflow_call`, so the caller intentionally has no Apple `secrets:` block. See [`SECRETS.md`](SECRETS.md).

## Trusted release context

The reusable release workflow accepts only a stable `vX.Y.Z` tag context. Configure a Ruleset for `v*` so published release tags cannot be moved or deleted casually.

The workflow additionally verifies:

- `app_path` is relative
- `dmg_name` is a basename ending in `.dmg`
- `CFBundleIdentifier` matches the configured bundle ID
- `CFBundleShortVersionString` matches the release tag without the leading `v`

Any mismatch blocks release before signing.

The `release` Environment should additionally restrict deployments to the intended protected release tags where supported.

## Versioning

Use stable SemVer tags initially:

```text
v1.0.0
v1.1.0
v1.1.1
```

The following values must agree before publishing:

- Git tag
- `CFBundleShortVersionString`
- release title/version
- Homebrew Cask `version`

Prerelease tags can be added later as a separate policy profile because Apple bundle-version rules and Homebrew prerelease behavior should be defined intentionally rather than inferred.

## DMG layout

The default packaging path uses Apple's built-in `hdiutil` to minimize third-party dependencies in the trusted release boundary.

The generated image contains:

- `<AppName>.app`
- an `/Applications` symlink

A styled DMG can be added later as an opt-in profile, but visual layout tooling must not weaken signing/notarization verification.

## Signing order

The expected order is:

```text
unsigned .app
  -> sign nested code if the project requires it
  -> sign root .app
  -> verify app signature
  -> create DMG
  -> sign DMG
  -> notarize DMG
  -> staple ticket
  -> verify DMG/ticket/Gatekeeper
```

The shared `sign-app.sh` intentionally does **not** use `codesign --deep` for signing. Applications with frameworks, helpers, XPC services, login items, system extensions, privileged helpers, or other nested code should add a project-specific inside-out signing adapter before the shared root-bundle signing step.

## Entitlements

Keep entitlements in the application repository because they define application capabilities, not generic release behavior.

Do not blindly reuse an entitlement file between unrelated applications. Review additions to entitlement files as security-sensitive changes.

## Failure handling

A failed notarization must stop publication. Preserve the notarization submission identifier and retrieve Apple's log for diagnosis.

Typical failure classes:

- unsigned nested component
- invalid/missing hardened runtime
- invalid entitlement
- certificate mismatch/expiration
- bundle metadata mismatch
- malformed DMG

Never bypass Gatekeeper/notarization checks to make a release green.

## Homebrew

Use a separate tap repository such as `Lamy210/homebrew-tap`.

`reusable-homebrew-update.yml` consumes the `.sha256` asset from the published GitHub Release, renders a Cask, pushes an automation branch to the tap, and opens a PR. It never receives Apple signing credentials.

See [`HOMEBREW.md`](HOMEBREW.md) for the tap CI and credential model.

## Rollback

Do not move a published tag. If a release is defective:

1. mark/remove the downloadable release if necessary
2. fix the source on a new PR
3. publish a new patch version
4. update Homebrew to the new version

For security incidents, rotate compromised credentials independently of application rollback.
