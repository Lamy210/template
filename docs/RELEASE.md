# macOS Release Pipeline

## Security model

The template uses a **two-stage workflow with three trust zones**. The application source commit and the privileged release-control commit are deliberately not the same trust decision.

A release tag chooses the application source to build. It must **not** choose the code that receives Apple credentials or repository write permission.

### Zone A: unprivileged tag build

`release-build.yml` runs on a stable `vX.Y.Z` tag push and has no release credentials, no `release` Environment, and no repository write permission.

It:

1. checks out the tag source;
2. builds/tests the unsigned application;
3. packages the `.app` into `unsigned-macos-app.tar.gz`;
4. writes strict build provenance;
5. uploads the archive and provenance under an artifact name bound to the exact workflow `run_id` and `run_attempt`.

The tag build is treated as **untrusted input production** from the privileged publisher's perspective. Even a tag that points to an older trusted ancestor can contain older build/release helper code, so this stage never receives Apple credentials or publication permission.

### Zone B: default-branch publisher validation

`release-publisher.yml` is triggered by `workflow_run` after `Release Build` completes successfully. This workflow must exist on the repository default branch.

The validation job is secret-free and read-only. Its control code comes from the current default-branch publisher commit, not from the release tag commit.

It independently validates:

- repository identity;
- canonical upstream workflow path and workflow ID;
- upstream event (`push`) and successful conclusion;
- exact upstream run ID and run attempt;
- upstream source SHA;
- exact non-expired artifact name and artifact ID;
- GitHub Artifact digest;
- Actions Artifact ZIP confinement;
- strict build-provenance schema;
- stable `vX.Y.Z` tag format;
- tag -> source-SHA binding;
- source reachability from the current trusted default-branch history;
- archive SHA-256;
- `.app` archive confinement and supported member types;
- `CFBundleIdentifier`;
- `CFBundleShortVersionString`;
- `CFBundleExecutable` safety/executable contract.

After validation, it creates **validator-owned metadata** and re-uploads only:

```text
validated-release-input/unsigned-macos-app.tar.gz
validated-release-input/validated-release-metadata.json
```

as a new artifact inside the publisher workflow run. That handoff separates untrusted upstream artifact retrieval/parsing from the later job that can access release credentials.

### Zone C: privileged signing and publication

The reusable macOS release workflow contains two separate privileged boundaries:

1. the **signing/notarization job** declares `environment: release`, receives Apple credentials, and is explicitly limited to `actions: read` + `contents: read`;
2. the later **GitHub publication job** does not declare the `release` Environment, receives no Apple credentials, and alone receives `contents: write`.

Before importing the Developer ID certificate, the signing job:

1. checks out trusted publisher control code at the publisher workflow SHA;
2. downloads the validator-owned artifact from the current publisher run;
3. revalidates the metadata against explicit publisher outputs;
4. re-hashes the archive;
5. repeats archive preflight/extraction;
6. repeats bundle ID/version/executable validation.

Only then does it import Apple credentials and perform signing/notarization. After final verification it uploads the signed DMG, checksum, and publisher-owned release provenance as an exact current-run/current-attempt Actions Artifact.

The publication job independently verifies that signer-produced artifact's ID, canonical name, GitHub digest, repository identity, publisher run, publisher attempt, and publisher SHA before downloading it. It then revalidates the trusted DMG basename, rebinds the immutable release tag, and performs GitHub Release publication.

The signing job must never execute scripts or hooks from the downloaded application archive. Release scripts and optional entitlements come from the trusted publisher/default-branch checkout. The publication job must never receive Apple signing/notarization credentials.

## Why the old monolithic workflow is retired

Do not use the old pattern:

```text
tag push
  -> build
  -> uses: ./.github/workflows/reusable-macos-release.yml
```

For a same-repository local reusable workflow, the called workflow is resolved from the caller's commit. On a tag-triggered run, that allows a newly-created tag pointing to an older ancestor to select older privileged release-control code.

`examples/app-release.yml` is therefore a migration pointer only. New adopters should copy/adapt both:

```text
examples/app-release-build.yml
  -> .github/workflows/release-build.yml

examples/app-release-publisher.yml
  -> .github/workflows/release-publisher.yml
```

The publisher file must be present on the default branch before relying on the two-stage release path.

### Historical ancestors before the split

A tag whose source commit predates `.github/workflows/release-build.yml` cannot produce a Release Build run for this two-stage pipeline. That is an intentional safe failure: no publisher validation run is created, and no privileged signing or publication path is entered.

Do not add a fallback that invokes an older tag-selected privileged workflow, reconstructs release input with historical privileged code, or restores the retired monolithic path merely to make pre-migration commits releasable.

The oldest commit eligible for automatic release should be an ancestor after the split Release Build workflow exists and after the two-stage release contract is available. If older source code must be shipped, migrate or rebuild it through reviewed current control code instead of weakening the trust boundary.

## End-to-end flow

```text
v1.2.3 tag push
  |
  v
Release Build (tag source, no secrets, read-only)
  |
  | unsigned-macos-release-<run-id>-<run-attempt>
  |   - unsigned-macos-app.tar.gz
  |   - build-provenance.json
  v
Release Publisher / validate (current default-branch control code)
  |
  | exact run/artifact resolution + provenance + tag + digest + app checks
  |
  | validated-release-input-<run-id>-<run-attempt>
  |   - unsigned-macos-app.tar.gz
  |   - validated-release-metadata.json
  v
Reusable macOS Release / sign (environment: release, contents: read)
  |
  | metadata/digest/archive revalidation
  | Apple signing -> DMG -> notarization -> verification
  | publisher-owned release-provenance.json
  | exact verified-macos-release-<publisher-run-id>-<publisher-run-attempt> artifact
  v
Reusable macOS Release / publish (no Apple secrets, contents: write)
  |
  | exact artifact identity + digest revalidation
  | release-tag rebinding
  v
Immutable GitHub Release
  |
  v
Reusable Homebrew Update
  |
  v
Homebrew tap PR
```

Homebrew runs only after signing/publication succeeds and receives the already-validated `source_tag` explicitly. It does not derive release identity from the publisher workflow's `github.ref_name`, because the publisher runs in default-branch context.

## Build provenance contract

Build provenance is strict and closed-schema. It binds the artifact to the expected release build identity, including:

- repository;
- workflow name/path;
- run ID;
- run attempt;
- event;
- source SHA/ref;
- stable tag/version;
- artifact name;
- archive name and SHA-256;
- application basename;
- bundle ID.

Unknown/missing fields, boolean-as-integer confusion, malformed hashes, unsafe basenames, inconsistent tag/ref/version fields, or a run/attempt mismatch are rejected.

The artifact name is derived from the exact source run identity:

```text
unsigned-macos-release-<run-id>-<run-attempt>
```

This prevents an old or unrelated artifact with a friendly generic name from being selected accidentally.

## Exact artifact resolution

The publisher does not trust only `github.event.workflow_run` display data or an artifact name.

`resolve-release-build-artifact.sh` queries GitHub and cross-checks the canonical workflow and exact run. It rejects:

- a different repository/head repository;
- a different workflow ID/path;
- a non-`push` event;
- a non-successful run;
- a different run attempt;
- malformed source SHA;
- missing/expired/ambiguous exact-name artifacts;
- artifact metadata bound to another run/SHA;
- malformed artifact digest;
- downloaded ZIP digest mismatch;
- ZIP traversal/symlink/duplicate/unexpected-file attacks;
- incomplete, malformed, or duplicate-ID artifact pagination;
- workflow runs advertising more than 1,000 artifacts before pagination;
- excessive source-artifact member count or declared uncompressed size.

The resolver writes source-artifact metadata itself; it does not accept source-owned claims for GitHub artifact ID/digest as authoritative.

## Tag and trusted-history binding

`verify-release-source.sh` resolves the stable tag independently and requires it to point to the exact source SHA validated from the upstream workflow run.

The source commit must also be reachable from the current trusted default-branch history. This policy permits intentionally releasing an older application commit that is still a trusted ancestor, while ensuring the **publisher control code remains current**.

If a project wants a stricter release-source policy later (for example only the current default-branch tip), add that as an explicit policy rather than assuming ancestry means freshness.

## Application archive contract

Do not upload a raw `.app` directory with `actions/upload-artifact`. Artifact storage does not preserve Unix executable mode reliably. Package the app first so `Contents/MacOS/*` permissions live inside the tar payload.

`extract-app-artifact.sh` treats the tar as hostile input. Before extraction it rejects:

- absolute paths;
- `..` traversal;
- members outside the expected `.app`;
- duplicate canonical member paths;
- symlinks escaping the app;
- hard links escaping the app;
- FIFOs/devices/other unsupported special members;
- archives above the configured member-count or extracted-file-byte limits.

The default application-archive limits are 100,000 members and 8 GiB of declared regular-file payload. Trusted publisher control code may lower or raise them with `MAX_APP_ARCHIVE_MEMBERS` and `MAX_APP_EXTRACTED_BYTES`; malformed or non-positive values fail closed. The outer Actions Artifact ZIP is separately capped to a small member set and roughly 4 GiB of declared uncompressed payload.

Legitimate in-bundle symlinks/hard links remain supported for normal macOS framework layouts.

After extraction, the executable named by `CFBundleExecutable` must be a non-symlink regular executable file. The privileged publisher repeats this validation before secrets and the final DMG verification repeats executable checks again.

## Validator-owned handoff

The secret-free validation job emits `validated-release-metadata.json`. It includes the exact validated identity needed by the privileged stage:

- source repository;
- source run ID/attempt;
- source SHA/tag/version;
- source artifact ID/digest;
- archive SHA-256;
- publisher SHA;
- app basename;
- bundle ID.

The privileged workflow compares metadata to explicit caller inputs and recomputes the actual archive digest before certificate import. A modified/mismatched re-handoff fails closed.

## Signing and notarization order

The expected privileged order is:

```text
validated archive
  -> reverify publisher-owned metadata + digest
  -> archive preflight/extract
  -> verify bundle ID/version/executable
  -> import certificate into temporary keychain
  -> sign nested code as required
  -> sign root .app
  -> verify app signature
  -> create DMG
  -> sign DMG
  -> notarize DMG
  -> staple ticket
  -> verify Gatekeeper/signature/executable
  -> generate SHA-256
  -> write publisher-owned release-provenance.json
  -> upload exact verified release artifact for this publisher run/attempt
  -> separate no-Apple-secrets publication job verifies artifact identity/digest
  -> rebind release tag
  -> publish immutable GitHub Release
```

The shared `sign-app.sh` intentionally does not use `codesign --deep` for signing. Apps with frameworks/helpers/XPC services/system extensions/privileged helpers need an explicit reviewed inside-out signing policy.

## Entitlements

Entitlements are security-sensitive publisher configuration. The default contract resolves `entitlements_path` from the trusted publisher/default-branch checkout, not from the untrusted release artifact.

Do not allow an application archive to supply executable release hooks or replace publisher entitlements.

## Final release attestation

After signing, notarization, stapling, and final release verification, the privileged publisher writes `release-provenance.json` from publisher-observed facts. This file is separate from the untrusted build provenance and is audit evidence rather than a replacement for runtime validation.

Its closed schema records:

- source repository;
- source run ID and run attempt;
- source SHA and stable tag;
- exact source Artifact ID and GitHub digest;
- validated unsigned archive SHA-256;
- publisher workflow run ID;
- trusted publisher SHA;
- SHA-256 recomputed from the final signed/notarized DMG.

The attestation intentionally omits a wall-clock timestamp and `publisherRunAttempt`. A full publisher rerun keeps the same workflow run ID but increments `github.run_attempt`; excluding attempt-local data keeps the attestation deterministic when all release facts and final DMG bytes are identical, preserving immutable/idempotent release retry behavior.

The verified Actions Artifact contains exactly the DMG, its checksum, and `release-provenance.json`. After exact-ID download, the separate no-Apple-secrets publication job rejects missing entries, unexpected extra entries, directories, and symlinked expected entries before interpreting provenance or mutating GitHub Release state.

Before any GitHub Release mutation, the publication job independently revalidates the final attestation against the expected source run/artifact/tag, current publisher run/SHA, and SHA-256 recomputed from the exact downloaded DMG. The attestation is therefore a checked handoff across the repository-write boundary rather than merely signer-authored metadata.

When GitHub Release publication is enabled, the DMG, checksum, and verified `release-provenance.json` are published as immutable release assets.

## GitHub Release immutability

Stable releases are append-never/replace-never.

`publish-github-release.sh`:

- requires the canonical `release-provenance.json` asset; omission or renaming fails before any GitHub call;
- requires the DMG, checksum, and provenance inputs to be regular non-symlink files;
- creates a missing release using the already-validated tag;
- treats an existing release as a no-op only when the expected DMG, checksum, and final release-attestation assets are byte-identical by SHA-256;
- fails when an expected asset is missing or differs;
- never uses `--clobber` for stable release assets.

A changed build needs a new version/tag.

## Homebrew ordering and identity

`reusable-homebrew-update.yml` runs after `sign-and-publish` succeeds. It receives `source_tag` explicitly from validator-owned release identity.

It:

1. validates the stable source tag and Cask/tap inputs;
2. checks out trusted publisher automation at the publisher SHA;
3. revalidates the GitHub Release as published, non-prerelease, exact-tag, and exact-three-asset state;
4. downloads the published DMG, checksum, and `release-provenance.json` for `source_tag`;
5. recomputes SHA-256 from the downloaded DMG and requires both the canonical checksum and final provenance to bind to those exact bytes and tag;
6. renders the Cask from that reverified digest;
7. creates/reuses an automation branch in the tap;
8. opens/reuses a tap PR.

It never receives Apple signing credentials.

## Retry semantics

### Release Build rerun

A rerun increments `run_attempt`, so it produces a different artifact identity:

```text
unsigned-macos-release-<same-run-id>-<new-attempt>
```

The publisher resolves the exact attempt that triggered it. It does not silently fall back to an older attempt.

### Publisher/signing retry

Retry the publisher with **Re-run all jobs** so the secret-free validation job runs again and creates a fresh validator-owned handoff bound to the current `github.run_attempt`.

Do not use `Re-run failed jobs` or rerun only `sign-and-publish` to reuse a previous attempt's validator artifact. The privileged verifier intentionally rejects a handoff from an older publisher attempt, because a retry must rerun provenance, tag, artifact, archive, and application validation rather than reuse an earlier trust decision.

The verified release artifact is also named with the publisher run ID and run attempt, so retries do not collide with an immutable Actions Artifact from a prior attempt.

Immutable GitHub Release publication makes a full retry safe after publication: identical assets are a no-op; different assets are rejected.

### Expired source artifact

Do not weaken validation or substitute another artifact. Rerun the unprivileged Release Build to create a new attempt and fresh exact artifact, then let the corresponding publisher run validate that attempt.

### Expired validator-owned artifact

If the publisher-run validated artifact has expired, rerun the validation/publisher path from a fresh upstream build attempt rather than manually recreating a similarly named artifact.

## Failure and recovery

Typical validation failures include:

- wrong repository/workflow/run/attempt;
- fork or unexpected head repository;
- source tag/SHA mismatch;
- source commit not reachable from trusted default-branch history;
- missing/expired/ambiguous artifact;
- artifact ZIP digest mismatch;
- build provenance mismatch;
- archive digest mismatch;
- unsafe ZIP/tar member/link/type;
- bundle ID/version/executable mismatch;
- publisher metadata mismatch;
- signing/notarization/Gatekeeper failure;
- attempted mutation of an existing stable GitHub Release.

For all trust failures, fail closed. Do not bypass provenance, archive, Gatekeeper, notarization, or immutable-release checks merely to make a release green.

If Apple notarization fails, retain the submission identifier and inspect Apple's notarization log before retrying.

## Production enablement gate: immutable release tags

Do not enable the two-stage publisher as a production release path until the effective GitHub Ruleset for `refs/tags/v*` has been verified in the target repository.

The effective release-tag policy must:

- allow initial creation of a new stable `vX.Y.Z` tag;
- reject update of an existing matching tag;
- reject deletion of an existing matching tag.

Verify the effective policy, not only a checked-in Ruleset JSON file. Use a disposable repository or disposable release tag to prove that initial creation succeeds while update and deletion are rejected.

Repeated runtime tag-to-SHA binding remains mandatory defense in depth, but it is not a substitute for immutable tag governance because GitHub ref lookup and release publication are not one atomic transaction.

If this Ruleset has not been verified, keep the privileged publisher disabled and do not treat the two-stage release path as production-ready.

## Disposable release Environment runtime policy proof

The read-only Environment doctor proves the configured policy shape, but GitHub's branch-policy list response may omit branch/tag type. Before production enablement, also prove the enforcement path in a **disposable repository**.

1. Configure the disposable repository's `release` Environment with the same selected-branch policy: only the default branch is allowed as a **Branch** rule.
2. Copy `examples/release-environment-proof.yml` to `.github/workflows/release-environment-proof.yml` on the disposable repository default branch.
3. Run:

```bash
bash scripts/release/prove-release-environment-policy.sh \
  --repository owner/disposable-release-proof \
  --confirm-disposable owner/disposable-release-proof
```

The example workflow contains two jobs and no secret references:

- `Baseline runner` does **not** reference an Environment and must succeed;
- `Release environment probe` references `environment: release` and contains only a trivial echo step.

The proof first dispatches the workflow from the repository default branch and requires both `Baseline runner` and `Release environment probe` to succeed. This positive control proves that the Environment is not accidentally configured to deny every ref.

It then creates a temporary branch and arbitrary tag at the same default-branch SHA and dispatches the same workflow from each unauthorized ref. For both refs it requires:

- the workflow itself to run;
- `Baseline runner` to succeed;
- the overall workflow to fail;
- `Release environment probe` to fail rather than enter the Environment.

Because all three refs point at the same commit and execute the same secret-free workflow, the deployment-ref identity is the material difference exercised by the proof. The script removes the temporary branch/tag in an EXIT cleanup path and refuses to target the current `GITHUB_REPOSITORY`.

This proof does not access Apple credentials and does not replace the read-only Environment doctor. Keep both checks: configuration-shape audit plus runtime evidence that the authorized default branch is admitted while unauthorized branch/tag refs are denied.

## Disposable post-split ancestor runtime proof

Before enabling the two-stage publisher for production, prove the architecture with a **disposable repository**. This proof is specifically about control-code selection; it is separate from Apple signing/notarization and from the immutable-tag Ruleset proof.

1. Put the current two-stage publisher on the disposable repository default branch.
2. Choose an older **post-split ancestor** that already contains `.github/workflows/release-build.yml` but predates the current publisher-control changes.
3. Create a canonical stable SemVer tag such as `v0.0.1` pointing to that ancestor.
4. Wait for that tag's **Release Build** run to complete successfully.
5. Wait for the downstream **Release Publisher** validation job to produce its `validated-release-input-...` artifact. The later signing/publication job may fail when the disposable repository intentionally has no Apple credentials; that does not invalidate this control-code proof.
6. Record the Release Build run ID and Release Publisher run ID.
7. Before advancing the disposable repository default branch again, run:

```bash
bash scripts/release/audit-post-split-runtime-proof.sh \
  owner/disposable-repo \
  SOURCE_RUN_ID \
  PUBLISHER_RUN_ID
```

The read-only proof collector verifies all of the following from GitHub API evidence and the publisher-owned validator artifact:

- source run is the successful same-repository `Release Build` push workflow at `.github/workflows/release-build.yml`;
- publisher run is the same-repository `workflow_run`-triggered `Release Publisher` at `.github/workflows/release-publisher.yml`;
- source SHA is a **strict ancestor** of the publisher SHA;
- publisher SHA equals the repository's current default-branch head at proof time;
- the validator Artifact name is bound to the exact publisher run/attempt and source run/attempt;
- the Artifact is non-expired and is itself bound to the publisher SHA/repository identity;
- `validated-release-metadata.json` binds the same source repository/run/attempt/SHA and publisher run/attempt/SHA.

A successful proof demonstrates the intended property:

> Historical post-split application bytes came from the tagged ancestor, while validation/control code came from the current default branch.

The command performs only reads and artifact download. It does not create/move/delete tags, mutate Rulesets, change Environments, or publish releases.

Run this proof immediately after the disposable test. Because it deliberately requires the publisher SHA to equal the **current** default-branch head, later default-branch commits make an old proof fail closed rather than silently treating stale evidence as current.

This proof does **not** replace the separate release-tag immutability test. The disposable repository must still prove that a newly-created `v*` tag can be created once but cannot later be updated or deleted.

## Migration checklist

For an adopter moving from the old monolithic example:

1. copy/adapt `examples/app-release-build.yml` to `.github/workflows/release-build.yml`;
2. copy/adapt `examples/app-release-publisher.yml` to `.github/workflows/release-publisher.yml` on the default branch;
3. configure app basename, bundle ID, signing identity, optional trusted entitlements path, DMG name, and Homebrew inputs;
4. keep Apple credentials only in the protected `release` Environment;
5. keep the tag-build workflow secret-free/read-only;
6. ensure the publisher validation job has only `actions: read` + `contents: read`;
7. verify only the signing/notarization job declares `environment: release`, that it has `contents: read` rather than write, and that the separate publication job has `contents: write` without Apple secrets;
8. run `bash scripts/release/audit-release-environment.sh owner/repo` and confirm the read-only doctor accepts the default-branch-only `release` Environment configuration;
9. in a disposable repository, run `prove-release-environment-policy.sh` and require the default branch to enter the `release` Environment while both an unauthorized branch and arbitrary tag are denied;
10. verify the effective `refs/tags/v*` Ruleset allows initial creation and rejects update/deletion;
11. run release-isolation tests before creating a real release tag;
12. use a disposable repository for destructive tag/ruleset tests;
13. before enabling the production publisher, perform the disposable post-split ancestor proof above, require `audit-post-split-runtime-proof.sh` to pass, and confirm the downstream run used the **current default-branch publisher** control code;
14. remove/ignore any copied legacy monolithic release workflow.

## Rollback

Do not move a published stable tag or replace published assets.

If a release is defective:

1. remediate the source on a reviewed change;
2. publish a new patch version;
3. update Homebrew to the new version.

For a credential/security incident, rotate compromised credentials independently from application rollback and review the publisher/default-branch control code before the next release.
