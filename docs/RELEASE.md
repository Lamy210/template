# macOS Release Pipeline

## Design principle

The release pipeline is split into two trust zones.

### Zone A: secret-free build

The application repository builds and tests the app without release credentials. The output is an **unsigned `.app` bundle packaged inside a `.tar.gz` archive** before it is handed to GitHub Actions Artifact.

Do not upload the `.app` directory directly with `actions/upload-artifact`. Actions Artifact storage does not preserve the executable mode of bundle files. Packaging the bundle first keeps the `Contents/MacOS/*` mode bits inside the tar payload while allowing the outer archive file itself to be normalized safely.

### Zone B: privileged release

A protected macOS release job downloads only that archive and performs:

1. archive member/link/type validation and extraction
2. `CFBundleExecutable` existence/executable-mode/non-symlink verification
3. temporary keychain creation
4. Developer ID certificate import
5. app signing
6. signature verification
7. DMG creation
8. DMG signing
9. Apple notarization
10. ticket stapling
11. Gatekeeper/signature/executable validation
12. SHA-256 generation
13. immutable GitHub Release publication
14. optional Homebrew Cask update

The privileged job must not execute arbitrary build/test commands supplied by the application repository or from the downloaded app artifact.

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
      - name: Package unsigned application
        env:
          APP_PATH: build/MyApp.app
          OUTPUT_ARCHIVE: build/unsigned-macos-app.tar.gz
        run: bash scripts/release/package-app-artifact.sh
      - uses: actions/upload-artifact@<full-commit-sha>
        with:
          name: unsigned-macos-app
          path: build/unsigned-macos-app.tar.gz

  release:
    needs: build
    permissions:
      contents: write
    uses: ./.github/workflows/reusable-macos-release.yml
    with:
      artifact_name: unsigned-macos-app
      artifact_archive_name: unsigned-macos-app.tar.gz
      app_name: MyApp
      app_path: MyApp.app
      bundle_id: com.example.MyApp
      dmg_name: MyApp-${{ github.ref_name }}.dmg
      signing_identity: "Developer ID Application: Example Developer (TEAMID1234)"
      entitlements_path: MyApp/MyApp.entitlements
```

See `examples/app-release.yml` for an end-to-end build → archived artifact handoff → signed release → Homebrew update example.

The called workflow's privileged job declares `environment: release` and reads Apple credentials directly from that protected Environment. GitHub does not support passing Environment secrets through `on.workflow_call`, so the caller intentionally has no Apple `secrets:` block. See [`SECRETS.md`](SECRETS.md).

## Artifact handoff contract

The unsigned application handoff is deliberately a single archive file:

```text
build/MyApp.app
  -> package-app-artifact.sh
  -> unsigned-macos-app.tar.gz
  -> actions/upload-artifact
  -> actions/download-artifact
  -> extract-app-artifact.sh
  -> release-input/MyApp.app
```

`extract-app-artifact.sh` treats the downloaded archive as untrusted input at the privileged boundary. Before extraction it rejects:

- absolute member paths;
- `..` traversal components;
- members outside the expected app bundle;
- symbolic-link targets that resolve outside the expected app bundle;
- hard-link targets that resolve outside the expected app bundle;
- special archive member types such as FIFOs/devices;
- an extracted top-level app symlink.

Regular files, directories, and app-internal symbolic/hard links remain supported so normal macOS framework layouts are not rejected merely for using links.

After extraction, the release workflow reads `CFBundleExecutable` from `Contents/Info.plist` and requires `Contents/MacOS/$CFBundleExecutable` to be a **non-symlink regular executable file**. `verify-release.sh` repeats the executable-mode check on both the signed source bundle and the exact application mounted from the final DMG.

The repository Quality workflow contains both a shell-level malicious-archive regression suite and a real Actions Artifact upload/download round-trip fixture. A change that reintroduces direct `.app` artifact handoff, permits an escaping archive link, accepts a special archive entry, or loses the executable bit must fail CI.

## Trusted release context

The reusable release workflow accepts only a stable `vX.Y.Z` tag context. Configure a Ruleset for `v*` so published release tags cannot be moved or deleted casually.

The workflow additionally verifies:

- `app_path` is a `.app` basename
- `artifact_archive_name` is a `.tar.gz` basename
- `dmg_name` is a basename ending in `.dmg`
- archive members and link targets remain under the expected app bundle
- archive member types are limited to the supported handoff contract
- `CFBundleIdentifier` matches the configured bundle ID
- `CFBundleShortVersionString` matches the release tag without the leading `v`
- `CFBundleExecutable` resolves to a non-symlink regular executable file

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
  -> verify executable permission after artifact handoff
  -> sign nested code if the project requires it
  -> sign root .app
  -> verify app signature
  -> create DMG
  -> sign DMG
  -> notarize DMG
  -> staple ticket
  -> verify DMG/ticket/Gatekeeper/executable permission
```

The shared `sign-app.sh` intentionally does **not** use `codesign --deep` for signing. Applications with frameworks, helpers, XPC services, login items, system extensions, privileged helpers, or other nested code need an explicit inside-out signing policy. A later template phase should represent that policy as reviewed signing data rather than executing arbitrary downloaded hooks in the privileged job.

## Entitlements

Keep entitlements in the application repository because they define application capabilities, not generic release behavior.

Do not blindly reuse an entitlement file between unrelated applications. Review additions to entitlement files as security-sensitive changes.

## GitHub Release immutability

A stable release version is append-never/replace-never after publication.

`publish-github-release.sh` enforces this contract:

- if the tag has no GitHub Release, create it with the verified DMG and `.sha256` asset;
- if the Release already exists and both assets are byte-for-byte identical by SHA-256, treat a rerun as a no-op;
- if either expected asset is missing, fail;
- if either existing asset differs from the newly verified artifact, fail;
- never use `gh release upload --clobber` for stable releases.

This keeps the immutable `vX.Y.Z` tag, downloadable DMG, checksum asset, and Homebrew Cask SHA aligned. A changed build must receive a new version/tag rather than replacing a published asset.

## Failure handling

A failed notarization must stop publication. Preserve the notarization submission identifier and retrieve Apple's log for diagnosis.

Typical failure classes:

- artifact handoff lost executable permission
- unsafe archive link or unsupported archive member type
- unsigned nested component
- invalid/missing hardened runtime
- invalid entitlement
- certificate mismatch/expiration
- bundle metadata mismatch
- malformed DMG
- attempted replacement of an existing stable release asset

Never bypass Gatekeeper/notarization/executable/archive-integrity checks to make a release green.

## Homebrew

Use a separate tap repository such as `Lamy210/homebrew-tap`.

`reusable-homebrew-update.yml` consumes the `.sha256` asset from the published GitHub Release, renders a Cask, pushes an automation branch to the tap, and opens a PR. It never receives Apple signing credentials.

See [`HOMEBREW.md`](HOMEBREW.md) for the tap CI and credential model.

## Rollback

Do not move a published tag or replace its release assets. If a release is defective:

1. mark/remove the downloadable release if necessary
2. fix the source on a new PR
3. publish a new patch version
4. update Homebrew to the new version

For security incidents, rotate compromised credentials independently of application rollback.
