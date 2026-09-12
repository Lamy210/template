# Homebrew Cask Distribution

## Repository model

Keep application source and Homebrew distribution metadata in separate repositories.

Recommended structure:

```text
Lamy210/MyApp
Lamy210/homebrew-tap
  Casks/
    my-app.rb
```

The application release workflow publishes the final notarized DMG first. A second workflow then updates the tap by opening a pull request.

## Why a pull request instead of direct push

The Cask update should not bypass tap validation. The expected path is:

```text
notarized GitHub Release
  -> compute/publish SHA-256
  -> render Cask
  -> push automation branch to tap
  -> open tap PR
  -> tap CI: style/audit/install checks
  -> merge
```

This separates application release credentials from tap write credentials and leaves an auditable review point before package metadata becomes public.

## Cask template

The reusable template lives at:

```text
templates/homebrew/Cask.rb.template
```

It renders the following data:

- Cask token
- application version
- SHA-256
- GitHub owner/repository
- DMG filename expression
- application display name
- description
- homepage
- bundle identifier

The renderer is:

```text
scripts/homebrew/render-cask.sh
```

It escapes values before inserting them into Ruby string literals and fails when an unresolved placeholder remains.

## Tap credential

`reusable-homebrew-update.yml` accepts one named secret: `tap_token`.

Preferred credential:

- short-lived GitHub App installation token
- installation limited to the tap repository
- only the contents/pull-request permissions actually required

Temporary fallback:

- fine-grained PAT
- restricted to the tap repository
- shortest practical lifetime

Do not reuse Apple signing/notarization credentials for this job, and do not pass `secrets: inherit`.

## Tap CI

The tap repository should independently validate generated Casks before merge. At minimum test:

- `brew style`
- `brew audit --cask` (use strict/online checks where appropriate)
- release URL download
- SHA-256 match
- Cask installation
- expected `.app` artifact name

For expensive install tests, run lightweight syntax/style checks on every PR and full installation checks on the automation Cask PR or before merge.

## User installation

With a tap named `Lamy210/homebrew-tap`, users can use the fully-qualified Cask name, for example:

```text
brew install --cask Lamy210/tap/my-app
```

The exact command depends on the tap and Cask token chosen for the application.

## Upgrade flow

For each stable release:

1. merge application changes to `main`
2. create protected tag `vX.Y.Z`
3. build unsigned `.app` without secrets
4. sign/notarize/package DMG
5. publish GitHub Release + `.sha256`
6. run Homebrew update workflow
7. review tap CI
8. merge tap PR

After the Cask update is merged, existing Homebrew users can receive the new version through the normal Homebrew upgrade flow.
