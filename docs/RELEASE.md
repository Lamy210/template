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

The application repository should have a workflow structured like this:

```yaml
jobs:
  build:
    runs-on: macos-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<full-commit-sha>
      - name: Build and test
        run: ./scripts/ci/build-release-artifact.sh
      - uses: actions/upload-artifact@<full-commit-sha>
        with:
          name: unsigned-macos-app
          path: path/to/MyApp.app

  release:
    needs: build
    uses: Lamy210/template/.github/workflows/reusable-macos-release.yml@<pinned-ref>
    with:
      artifact-name: unsigned-macos-app
      app-name: MyApp
      bundle-id: com.example.MyApp
    secrets:
      certificate-p12-base64: ${{ secrets.MACOS_CERTIFICATE_P12_BASE64 }}
      certificate-password: ${{ secrets.MACOS_CERTIFICATE_PASSWORD }}
      app-store-connect-api-key-p8: ${{ secrets.APP_STORE_CONNECT_API_KEY_P8 }}
      app-store-connect-key-id: ${{ secrets.APP_STORE_CONNECT_KEY_ID }}
      app-store-connect-issuer-id: ${{ secrets.APP_STORE_CONNECT_ISSUER_ID }}
```

The example is intentionally explicit about each secret. Do not replace the secret mapping with `secrets: inherit`.

## Versioning

Use SemVer tags:

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

A mismatch is a release blocker.

## DMG layout

The default packaging path uses Apple's built-in `hdiutil` to minimize third-party dependencies in the trusted release boundary.

A styled DMG can be added later as an opt-in profile, but visual layout tooling must not weaken signing/notarization verification.

## Signing order

The expected order is:

```text
unsigned .app
  -> sign nested code/app
  -> verify app signature
  -> create DMG
  -> sign DMG
  -> notarize DMG
  -> staple ticket
  -> verify DMG/ticket/Gatekeeper
```

Applications with helpers, XPC services, frameworks, login items, system extensions, or privileged helpers may require project-specific nested signing logic. Such cases should extend the signing step rather than disabling verification.

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

Release automation should generate/update a Cask using the final notarized DMG URL and SHA-256, then open a PR to the tap. Prefer PR + CI over direct push to the tap default branch.

The Cask pipeline should verify at minimum:

- Cask syntax
- `brew audit`
- download checksum
- installability
- app artifact name

## Rollback

Do not move a published tag. If a release is defective:

1. mark/remove the downloadable release if necessary
2. fix the source on a new PR
3. publish a new patch version
4. update Homebrew to the new version

For security incidents, rotate compromised credentials independently of application rollback.
