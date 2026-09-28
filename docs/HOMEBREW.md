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

The renderer also requires an explicit trusted `CASK_OUTPUT_ROOT`. Before creating the parent directory and again immediately before writing, it validates that the output stays lexically below that root and that the root, every existing parent component, and any existing target are not symlinks. Existing parents must be directories and an existing target must be a regular file. This prevents a tap-controlled `Casks/` symlink or Cask-file symlink from redirecting the generated output into the trusted publisher checkout or another workspace path.

## Release identity contract

`reusable-homebrew-update.yml` requires a validated `source_tag` input in stable `vX.Y.Z` form.

It does not use:

```text
github.ref_name
GITHUB_REF_NAME
GITHUB_REF_TYPE
```

to determine the application release version.

The updater resolves the GitHub REST Release object for exactly `source_tag` once, snapshots the positive numeric Release ID and the exact three expected asset IDs, GitHub-provided SHA-256 digests, sizes, and canonical API/download URLs, then downloads each asset through `/releases/assets/<asset_id>` rather than resolving it again by tag/name. Each downloaded file must match the snapshotted GitHub digest and size. After all downloads, the updater re-fetches the same numeric Release ID and requires the complete download manifest to remain byte-for-byte identical before using the DMG/checksum/provenance. The source repository numeric ID/full name is also rebound before and after this unit.

The updater then renders the Cask from the same validated `source_tag` and published checksum and names the tap automation branch from that identity. This prevents the default-branch publisher's own ref context from being mistaken for the released application tag and prevents a release/asset replacement race between metadata lookup and download.

The Cask filename template is also bound to the exact published DMG identity. Before the Homebrew tap credential is used, the updater expands the single required `#{version}` placeholder in `dmg_basename_template` with the validated `source_tag` version and requires the result to equal `dmg_name` byte-for-byte. A configuration such as:

```text
source_tag=v1.2.3
dmg_name=MyApp-v1.2.3.dmg
dmg_basename_template=Other-v#{version}.dmg
```

fails before any tap branch write or pull-request operation. This prevents a verified release asset and the generated Cask URL from drifting to different filenames.

The Cask application identity is rebound separately. The publisher validation job exports its validator-owned `appBasename` and `bundleId` only as comparison evidence. Before the tap token is exposed, the Homebrew updater requires:

```text
app_name + ".app" == validated_app_basename
bundle_id          == validated_bundle_id
```

The trusted Homebrew `app_name` and `bundle_id` remain the values used to render the Cask. Validator-owned values are not allowed to silently redefine publisher policy; a disagreement fails closed instead.

## Published asset download contract

The exact downloader is:

```text
scripts/release/download-exact-release-assets.sh
```

It treats GitHub REST Release metadata as a closed identity snapshot before the tap credential is used. The snapshot requires:

- one positive numeric Release ID;
- the exact stable `source_tag`;
- published/non-prerelease state;
- a boolean native `immutable` flag recorded as evidence (native immutability is not yet required by this consumer contract);
- exactly the expected DMG, checksum, and `release-provenance.json` names;
- one unique positive asset ID per name;
- `state=uploaded`;
- positive size;
- GitHub `sha256:<64 lowercase hex>` digest;
- canonical repository-bound API URL and browser download URL.

Downloads use the snapshotted asset IDs directly and verify both bytes and size. They are written only into a hidden staging directory beside the requested output path. The same numeric Release ID is then resolved again, the canonical manifest and repository identity must remain unchanged, and temporary metadata cleanup must succeed before the staging directory is renamed into the final output directory. That rename is the publication commit point: no fallible filesystem cleanup runs afterward. Any failed digest/size/API/identity/temporary-cleanup check removes staging and leaves no partially trusted output directory behind. Tag-name pattern downloads such as `gh release download --pattern` are intentionally not part of this path.

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

1. resolves the tap through the GitHub REST repository endpoint before cloning, validates its canonical `full_name` and configured default branch, reconstructs the only accepted GitHub HTTPS/SSH clone URLs from that `full_name` and requires the REST `clone_url`/`ssh_url` fields to match exactly, then snapshots the positive numeric repository ID;
2. clones the tap and immediately re-resolves the same repository metadata, requiring the numeric ID to equal the snapshot and the effective `origin` fetch/push URLs to match only the canonical GitHub HTTPS clone URL, its exact no-`.git` web form, or the canonical GitHub SSH clone URL for that same repository; doubled `.git` suffixes, alternate SSH syntax, Git URL rewrites, mirrors, repository replacement, or additional push destinations fail closed;
3. fetches the tap repository and records the current remote automation-branch SHA if that branch already exists;
4. rebuilds the local automation branch from the trusted tap default branch, never from the existing automation branch;
5. renders only the intended Cask change;
6. revalidates the same numeric repository ID, canonical repository/default-branch identity, and effective origin remote before branch mutation, after no-op cleanup, around pull-request mutation, and during final acceptance;
7. updates an existing automation branch with an exact-SHA `--force-with-lease`, so a concurrent or unexpected remote rewrite causes the run to fail instead of being overwritten;
8. immediately before creating a tap pull request, re-reads the automation branch and requires it to still equal the exact trusted pushed commit; every paginated PR payload is also bound to the captured tap repository numeric ID for both base and same-repository head identity, and the workflow repeats the repository/remote/branch preflight after the create attempt before accepting the PR identity.

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

A retry also re-snapshots the tap repository numeric ID for that workflow run. Within one run, any change from the captured repository ID, canonical name/default branch, effective remote, or trusted automation-branch SHA aborts before another write is accepted.
