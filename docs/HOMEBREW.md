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

The application release publisher signs/notarizes and publishes the immutable GitHub Release first. Only after that succeeds does the publisher invoke the Homebrew updater.

## Ordering in the isolated release pipeline

The expected path is:

```text
vX.Y.Z tag
  -> secret-free Release Build
  -> default-branch publisher validation
  -> protected signing/notarization
  -> immutable GitHub Release + .sha256
  -> Homebrew updater(source_tag=<validated tag>)
  -> render Cask
  -> push automation branch to tap
  -> open tap PR
  -> tap CI
  -> merge
```

The Homebrew updater must not infer the release identity from its own `github.ref_name`. In the two-stage design it runs from the default-branch publisher context, so it receives the already-validated stable tag explicitly as `source_tag`.

## Why a pull request instead of direct push

The Cask update should not bypass tap validation. A tap pull request keeps application release credentials separate from tap write credentials and leaves an auditable review point before package metadata becomes public.

## Cask template

The reusable template lives at:

```text
templates/homebrew/Cask.rb.template
```

It renders:

- Cask token
- validated application version
- release SHA-256
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

## Release identity contract

`reusable-homebrew-update.yml` requires a validated `source_tag` input in stable `vX.Y.Z` form.

It does not use:

```text
github.ref_name
GITHUB_REF_NAME
GITHUB_REF_TYPE
```

to determine the application release version.

The updater downloads `${dmg_name}.sha256` from the immutable GitHub Release for exactly `source_tag`, renders the Cask from that version/checksum, and names the tap automation branch from the same validated identity.

This prevents the default-branch publisher's own ref context from being mistaken for the released application tag.

## Published checksum contract

The Homebrew updater treats the published `.sha256` asset as structured release metadata, not as an arbitrary text file.

The release producer writes the checksum with `shasum -a 256 <DMG basename>`. The consumer requires exactly one canonical line:

```text
<64 lowercase hexadecimal characters><two spaces><exact DMG basename>
```

with one trailing newline and no additional content. The filename embedded in the checksum must exactly equal the validated `dmg_name`. Uppercase digests, alternate prefixes such as `sha256:`, additional lines, missing trailing newline, unexpected spacing, and a checksum for a different asset are rejected before the tap write credential is used.

The parser lives at `scripts/homebrew/parse_release_checksum.py` and is covered independently from the workflow contract.

## Trusted automation checkout

The updater checks out release automation at the publisher workflow SHA with persisted credentials disabled. The release tag artifact does not provide Homebrew scripts or templates to the privileged update path.

The Homebrew job depends on both:

- publisher validation; and
- successful signing/publication.

A failed or rejected release must not produce a tap update PR.

## Tap credential

`reusable-homebrew-update.yml` accepts one named secret:

```text
tap_token
```

Preferred credential:

- short-lived GitHub App installation token
- installation limited to the tap repository
- only the contents/pull-request permissions actually required

Temporary fallback:

- fine-grained PAT
- restricted to the tap repository
- shortest practical lifetime

Do not reuse Apple signing/notarization credentials for this job. Do not use `secrets: inherit`; pass only the narrow named `tap_token` interface.

## Automation branch trust model

The predictable `automation/<cask>-v<version>` branch name is an output location, not trusted input.

On every run, the updater:

1. fetches the tap repository and records the current remote automation-branch SHA if that branch already exists;
2. rebuilds the local automation branch from the trusted tap default branch, never from the existing automation branch;
3. renders only the intended Cask change;
4. updates an existing automation branch with an exact-SHA `--force-with-lease`, so a concurrent or unexpected remote rewrite causes the run to fail instead of being overwritten.

If the existing automation branch contains stale or unrelated commits, those commits are not carried forward. If the desired Cask is already identical, an existing remote automation branch is still reset to the trusted default-branch state using the same lease check.

This limited history rewrite applies only to the dedicated automation branch. Do not use this behavior for the tap default branch or a human-owned feature branch.

## Tap CI

The tap repository should independently validate generated Casks before merge. At minimum test:

- `brew style`
- `brew audit --cask` (strict/online checks where appropriate)
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

1. merge application changes to the trusted default branch;
2. create protected immutable tag `vX.Y.Z`;
3. run the secret-free Release Build;
4. let the default-branch publisher validate the exact build run/artifact and source tag;
5. sign/notarize/package the DMG in the protected `release` Environment;
6. publish the immutable GitHub Release + `.sha256`;
7. invoke Homebrew with the validated `source_tag`;
8. review tap CI;
9. merge the tap PR.

After the Cask update is merged, existing Homebrew users can receive the new version through the normal Homebrew upgrade flow.

## Retry behavior

If release publication already exists with byte-identical assets, the release publisher treats publication as an idempotent no-op. A subsequent Homebrew invocation should render the same version/checksum and reuse or produce no change in the existing tap automation branch.

If the release asset differs, publication fails closed and the Homebrew job does not run. Do not update the Cask to a replacement asset under an existing stable version; publish a new version instead.
