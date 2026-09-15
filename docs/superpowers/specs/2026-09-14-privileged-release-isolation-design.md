# Privileged macOS Release Isolation Design

**Status:** Proposed

**Issue:** #5 — `design: isolate privileged release from tag commit workflow code`

**Scope:** Architectural security redesign of the generated macOS release template. This document defines the trust boundary and acceptance criteria only; it does not implement the workflow change.

## 1. Problem statement

The current generated release example is triggered by a version-tag push and calls a same-repository reusable workflow using a local path such as:

```yaml
uses: ./.github/workflows/reusable-macos-release.yml
```

For a same-repository local reusable workflow, GitHub resolves the called workflow from the same commit as the caller. A tag-triggered run therefore selects release-control workflow and script versions from the commit referenced by the tag.

PR #3 already verifies that the tag commit is contained in the trusted release branch, but ancestry does not guarantee that the privileged release-control code is current. A newly-created `vX.Y.Z` tag can point to an older trusted ancestor and therefore select older signing/notarization/release logic.

The security problem is not that an old application commit can be released. The problem is that the application commit currently also selects the code that receives Apple signing credentials and repository write permission.

## 2. Security objective

Separate **application source selection** from **privileged release-control code selection**.

The final system MUST guarantee:

1. The release tag chooses the application source commit, but does not choose the privileged publisher implementation.
2. Apple signing/notarization credentials are unavailable to the tag-build workflow.
3. Repository write permission is unavailable to the tag-build workflow.
4. The privileged publisher is defined by the current default-branch workflow, not by the release tag commit.
5. The publisher consumes one exact successful build run and one exact artifact from that run.
6. Repository, workflow identity, event type, run ID/attempt, source SHA, version tag, artifact identity and artifact digests are cross-validated before privileged work starts.
7. The privileged job never executes scripts from the release tag checkout.
8. PR #3 archive confinement and immutable publication guarantees remain in force.
9. Fork pull requests and arbitrary untrusted workflow runs cannot reach the release Environment.
10. Retrying a legitimate release remains idempotent and auditable.

## 3. Non-goals

This phase does not:

- introduce a central hosted reusable workflow shared by every generated repository;
- grant a permanent Ruleset bypass actor;
- make GitHub Ruleset administration automatic;
- sign arbitrary artifacts from external repositories;
- execute application build scripts in the privileged publisher;
- redesign Homebrew tap governance beyond moving its invocation to the trusted publication side when necessary;
- support mutable release tags.

## 4. GitHub Actions behavior relied upon

The design relies on current GitHub Actions semantics:

- a same-repository reusable workflow referenced through `./.github/workflows/...` uses the same commit as its caller;
- a `workflow_run` workflow only triggers when its workflow file exists on the default branch;
- for `workflow_run`, `GITHUB_REF` is the default branch and `GITHUB_SHA` is the last commit on the default branch;
- a `workflow_run` workflow may have secrets and a write-capable token even when the triggering workflow did not;
- GitHub explicitly warns that privileged `workflow_run` workflows must not blindly trust code, caches or artifacts produced by the preceding workflow.

Therefore `workflow_run` is useful here only when the downstream workflow treats every triggering-run field and artifact as untrusted input until validation succeeds.

## 5. Considered designs

### A. Two-stage `workflow_run` publisher — selected

1. Tag push runs an unprivileged release-build workflow.
2. Successful completion triggers a default-branch `workflow_run` publisher.
3. A secret-free validation job verifies provenance and re-handoffs the exact archive.
4. Only then does a separate macOS job enter the `release` Environment and sign/publish.

This preserves automated version-tag releases while separating source commit from publisher implementation.

### B. Repository dispatch from the tag build — rejected

A tag-build workflow would need permission/credentials to dispatch the privileged workflow. That weakens the boundary we are trying to establish and creates another authenticated command channel from tag-selected code.

### C. Public/central reusable publisher pinned by SHA — deferred

A central publisher could provide strong code-version pinning, but it would create a new product-level dependency for every generated repository. The current template model is repository-local, so this is not the Phase 1 default.

### D. Manual `workflow_dispatch` publication only — not the default

This can be secure when carefully validated but gives up the normal automatic release flow. It may be added later as a recovery entry point that accepts an exact build-run ID and performs the same validation path.

## 6. Selected architecture

```text
version tag vX.Y.Z
        |
        v
+---------------------------+
| Release Build             |
| trigger: push tag         |
| source: tag commit        |
| permissions: contents:r   |
| secrets: none             |
+-------------+-------------+
              |
              | exact build artifact
              | archive + build-provenance.json
              v
+---------------------------+
| Release Publisher         |
| trigger: workflow_run     |
| definition: default branch|
+-------------+-------------+
              |
      +-------+--------+
      | Validate Input |
      | no environment |
      | actions:r      |
      | contents:r     |
      +-------+--------+
              |
              | validated archive + exact digest
              v
      +----------------+
      | Sign & Publish |
      | macOS          |
      | env: release   |
      | contents:w     |
      +----------------+
```

The validation job and signing job MUST remain separate jobs. This ensures Apple credentials are not injected into the process that first parses the triggering run and its external artifact.

## 7. Stage A — unprivileged Release Build

### Trigger

```yaml
on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"
```

### Permissions

Workflow-level default:

```yaml
permissions: {}
```

Build job:

```yaml
permissions:
  contents: read
```

No Environment is attached. No Apple signing credential, GitHub Release write permission or Homebrew tap token is available.

### Responsibilities

The tag-build workflow:

1. checks out the tag commit;
2. builds and tests the unsigned application;
3. packages the `.app` using the PR #3 tar handoff;
4. computes SHA-256 for the tar archive;
5. writes a deterministic `build-provenance.json`;
6. uploads one uniquely named Actions Artifact.

Artifact names MUST include the build run ID and run attempt to avoid ambiguity across re-runs:

```text
unsigned-macos-release-<run-id>-<run-attempt>
```

The artifact contains exactly:

```text
release-input/
  unsigned-macos-app.tar.gz
  build-provenance.json
```

The workflow MUST NOT sign, notarize, create a GitHub Release, modify tags, or update Homebrew.

## 8. Build provenance schema

`build-provenance.json` is a claim made by the unprivileged build and is never trusted on its own.

Version 1:

```json
{
  "schemaVersion": 1,
  "repository": "owner/repo",
  "sourceWorkflowName": "Release Build",
  "sourceWorkflowPath": ".github/workflows/release-build.yml",
  "sourceRunId": 123456789,
  "sourceRunAttempt": 1,
  "sourceEvent": "push",
  "sourceSHA": "0123456789abcdef0123456789abcdef01234567",
  "sourceRef": "refs/tags/v1.2.3",
  "tag": "v1.2.3",
  "artifactName": "unsigned-macos-release-123456789-1",
  "archiveName": "unsigned-macos-app.tar.gz",
  "archiveSha256": "sha256:<64 lowercase hex>",
  "appBasename": "MyApp.app",
  "bundleId": "com.example.MyApp",
  "version": "1.2.3"
}
```

Canonical JSON rules and field validation SHOULD be strict. Unknown fields are rejected in the first schema version so security-relevant meaning cannot drift silently.

The artifact ID and GitHub Artifact digest are intentionally not included: they do not exist until after upload. The publisher obtains them independently from GitHub.

## 9. Stage B — default-branch Release Publisher

### Trigger

```yaml
on:
  workflow_run:
    workflows: ["Release Build"]
    types: [completed]
```

Do not rely on a branch filter for version tags. The publisher validates the source tag and source SHA explicitly.

The publisher workflow exists on the default branch. It MUST NOT be invoked through a local reusable workflow selected by the release tag commit.

### Workflow permissions

```yaml
permissions: {}
```

Permissions are granted only per job.

## 10. Validation job — no release secrets

The first publisher job has no Environment and only:

```yaml
permissions:
  actions: read
  contents: read
```

It MUST fail closed unless every condition below succeeds.

### 10.1 Triggering-run identity

Validate the `workflow_run` event and then re-fetch the run through the GitHub API. Require:

- `conclusion == success`;
- event is `push`;
- triggering repository ID and full name equal the current repository;
- triggering run ID equals the event run ID;
- run attempt equals the event run attempt;
- source SHA is exactly 40 lowercase hexadecimal characters;
- head repository is the current repository, not a fork;
- workflow ID equals the workflow ID resolved from the canonical current path `.github/workflows/release-build.yml`;
- workflow path/name are the expected canonical build workflow.

Matching only a human-readable workflow name is insufficient because names are not a durable security identity.

### 10.2 Version tag binding

Read the tag from provenance only as a candidate, then independently verify:

- it matches `^v[0-9]+\.[0-9]+\.[0-9]+$`;
- provenance `sourceRef == refs/tags/<tag>`;
- provenance `version == <tag without v>`;
- the repository's Git ref for the tag resolves to `workflow_run.head_sha`;
- annotated tags are fully dereferenced to their commit before comparison;
- the source commit is reachable from the current default branch.

The current default-branch head is the release-policy/control source. The application commit may be an older ancestor, but it cannot select the publisher code.

### 10.3 Exact artifact resolution

List artifacts for the exact triggering run. Require:

- exact expected artifact name `unsigned-macos-release-<run-id>-<run-attempt>`;
- exactly one matching non-expired artifact;
- artifact metadata belongs to the triggering run;
- artifact digest, when provided by GitHub, has valid `sha256:<hex>` syntax;
- no fallback to a similarly named artifact or another run.

Download the exact artifact through the GitHub API into a fresh temporary directory.

Before extraction, validate the Actions Artifact ZIP using the same fail-closed principles already used elsewhere in the template: reject absolute paths, traversal, duplicate canonical paths, symlink-based escape and malformed archive structure.

### 10.4 Provenance cross-check

Read `build-provenance.json` only after ZIP confinement checks. Every security-relevant field is cross-checked against independently known GitHub data or publisher configuration:

- repository;
- workflow identity/path;
- run ID;
- run attempt;
- event;
- source SHA;
- tag/ref;
- artifact name;
- archive name;
- app basename;
- bundle ID;
- version.

A self-consistent provenance file is not sufficient.

### 10.5 Archive digest and PR #3 preflight

Compute SHA-256 over the downloaded `unsigned-macos-app.tar.gz` and require exact equality with `archiveSha256`.

Then run the PR #3 archive preflight. It must continue to reject:

- out-of-bundle paths and traversal;
- escaping symlinks;
- escaping hard links;
- FIFO/device/unsupported special entries;
- duplicate canonical member paths;
- unsafe bundle executable structure.

No signing secret is available in this job.

### 10.6 Validated handoff

After validation, upload the **unchanged, digest-verified tar archive** into a new artifact owned by the publisher run, using a unique name such as:

```text
validated-release-input-<source-run-id>-<source-run-attempt>
```

Also emit a small validator-generated metadata file containing at minimum:

- source run ID/attempt;
- source SHA/tag;
- source artifact ID and GitHub digest when available;
- archive SHA-256;
- publisher workflow SHA;
- validation timestamp.

The signing job MUST use only this current-publisher-run artifact, never download the original build artifact directly.

## 11. Signing and publication job — privileged boundary

This job:

- `needs: validate-release-input`;
- attaches `environment: release`;
- runs on macOS;
- receives Apple signing/notarization credentials only here;
- receives repository write permission only here.

Suggested permissions:

```yaml
permissions:
  actions: read
  contents: write
```

### Trusted control checkout

Checkout the publisher workflow's own trusted commit (`github.sha`, which for `workflow_run` is the default-branch commit associated with the publisher run).

Never checkout the release tag commit into the directory from which shell scripts are executed.

The release tag commit is application data, not privileged control code.

### Re-verification before secret use

After downloading the validator-produced artifact:

1. verify its expected unique name;
2. recompute the archive SHA-256 and compare to validator metadata;
3. rerun archive preflight before extraction;
4. verify `CFBundleIdentifier`, version and executable contract;
5. only then import the Developer ID certificate and begin signing.

This is defense in depth against handoff corruption between jobs.

### Entitlements

The default template uses the entitlements file from the trusted publisher/default-branch checkout. The tag-build artifact does not get to inject an arbitrary entitlements file into the privileged job.

An adopter that must reproduce historical entitlements needs a separately reviewed extension; it is not the portable default because entitlements directly influence the capabilities granted by the Developer ID signature.

### Final publication

Preserve PR #3 behavior:

- sign application;
- create and sign DMG;
- notarize and staple;
- verify mounted DMG payload and executable;
- generate SHA-256;
- publish GitHub Release immutably/idempotently;
- never `--clobber` existing release assets.

Homebrew update occurs only after verified immutable publication and must use current trusted workflow/control code.

## 12. Final release attestation

The publisher SHOULD emit `release-provenance.json` with publisher-observed facts, separate from the untrusted build provenance.

Suggested fields:

```json
{
  "schemaVersion": 1,
  "sourceRepository": "owner/repo",
  "sourceRunId": 123456789,
  "sourceRunAttempt": 1,
  "sourceSHA": "...",
  "tag": "v1.2.3",
  "sourceArtifactId": 987654321,
  "sourceArtifactDigest": "sha256:...",
  "archiveSha256": "sha256:...",
  "publisherRunId": 22334455,
  "publisherSHA": "...",
  "dmgSha256": "sha256:..."
}
```

This file can be attached to the GitHub Release alongside the DMG/checksum in a later implementation step. It is audit evidence, not a replacement for runtime checks.

## 13. Re-run and concurrency behavior

- Artifact names include run ID and run attempt.
- The publisher consumes only the exact completed attempt that triggered it.
- Publisher concurrency is grouped by triggering build run ID with `cancel-in-progress: false`.
- Re-running the build produces a new run attempt and therefore a new unique artifact name.
- Re-running the publisher is safe because final GitHub Release publication is immutable/idempotent.
- A publisher retry MUST rerun all provenance and digest checks; it cannot reuse a previous job's trust decision implicitly.

## 14. Failure and recovery

### Invalid provenance or artifact

Fail before entering the `release` Environment. Do not attempt to repair or reinterpret malformed input.

### Build artifact expired

Re-run the unprivileged build for the same immutable tag if GitHub still permits the run to be re-executed. The resulting run attempt is validated independently. Never recreate/move the tag merely to obtain a new artifact.

### Publisher failed after signing but before release publication

Re-run the publisher. Notarization/signing may repeat; immutable release publication guarantees that identical final assets become a no-op and changed assets fail closed.

### GitHub Release already exists with different assets

Stop and require operator investigation. Do not replace assets automatically.

### Default branch advances during publication

The publisher run remains bound to the default-branch `github.sha` from which its workflow/control code was loaded. It does not silently switch control logic mid-run.

## 15. Threat model

| Threat | Required mitigation |
| --- | --- |
| New tag points to an old trusted ancestor | Publisher code comes from default branch, not tag commit |
| Fork/untrusted PR tries to obtain Apple secrets | Publisher only accepts exact same-repo successful Release Build workflow_run |
| Workflow with same display name impersonates build | Compare workflow ID resolved from canonical build-workflow path |
| Build provenance lies about SHA/tag/run | Cross-check every field against event/API/ref data |
| Artifact from another run is substituted | Exact run-scoped unique artifact name + artifact ID/digest checks |
| Artifact bytes change after provenance creation | Recompute archive SHA-256 in validator and signer |
| Archive path/link exploit targets signing runner | PR #3 preflight before extraction, repeated in privileged job |
| Build injects signing policy through entitlements | Entitlements come from trusted publisher/default branch |
| Existing Release is overwritten | PR #3 immutable/idempotent publication; no clobber |
| Validation parser compromise reaches Apple secrets | Validation is a separate job with no release Environment |

## 16. Rollout plan

1. Land PR #3 release/archive hardening first.
2. Land repository-governance Ruleset work separately.
3. Add the new unprivileged `release-build.yml` and default-branch `release-publisher.yml` in a dedicated implementation PR.
4. Initially keep the old release example disabled/renamed rather than running both publication paths concurrently.
5. Exercise the two-stage path with a disposable test repository or non-production signing setup before an adopter's first real release.
6. Verify that a newly-created tag pointing to an older default-branch ancestor still causes the publisher to execute the current default-branch control workflow.
7. Verify exact-run artifact provenance failures are fail-closed.
8. Switch the documented generated-template release path to the two-stage model.
9. Remove the obsolete tag-selected privileged workflow path.

## 17. Acceptance tests for implementation

Implementation is not complete until automated tests cover at least:

- wrong triggering repository rejected;
- wrong workflow ID/path rejected;
- non-push event rejected;
- unsuccessful triggering run rejected;
- malformed run ID/attempt/SHA rejected;
- wrong/moved/missing tag rejected;
- tag SHA != workflow_run head SHA rejected;
- source SHA not reachable from current default branch rejected;
- zero/multiple/expired matching artifacts rejected;
- artifact digest mismatch rejected;
- provenance run ID/attempt/SHA/tag mismatch rejected;
- archive digest mismatch rejected;
- existing PR #3 archive hostile fixtures remain rejected;
- validation job has no release Environment/secrets/write permission;
- signing job consumes only validator-produced artifact;
- privileged checkout is default-branch publisher SHA, not source tag SHA;
- immutable publication regression remains green;
- retry with identical final assets is a no-op;
- old-ancestor tag test proves current publisher control code is selected.

## 18. Implementation boundaries

After this design is approved, implementation should be split so trust decisions are reviewable:

1. provenance schema + pure validator + hostile fixtures;
2. exact triggering-run/artifact resolver;
3. unprivileged release-build workflow;
4. publisher validation workflow/job;
5. privileged signing/publication job migration;
6. final release attestation and documentation;
7. adopter validation.

Do not combine the architectural migration with unrelated visual-regression or Ruleset feature work.

## 19. Decision

Adopt the two-stage `workflow_run` architecture as the template's next release-security design:

> **Tag commit selects application bytes; current default branch selects privileged release-control code.**

The implementation must preserve a strict no-secret validation stage before the `release` Environment and must bind publication to one exact successful same-repository build run, immutable tag, source SHA, artifact identity and artifact digest.