# Privileged Release Isolation — Security Review Addendum

**Status:** Required amendments to the proposed design in `2026-09-14-privileged-release-isolation-design.md`.

This addendum records security-review findings that must be treated as part of the approved design before implementation begins.

## 1. Production enablement requires immutable release tags

The two-stage publisher MUST NOT become the production release path until the effective GitHub Ruleset for `refs/tags/v*` has been verified to prohibit both update and deletion of an existing release tag.

Creating a new version tag remains allowed. Moving or deleting an existing version tag does not.

This makes tag immutability a prerequisite of production enablement rather than a later hardening option.

Reason: validating `tag -> source SHA` once is not sufficient if the tag can move while signing/notarization is in progress.

## 2. Repeat tag binding at privileged boundaries

Even with the immutable-tag Ruleset enabled, the publisher MUST re-resolve the version tag independently:

1. in the secret-free validation job;
2. again in the signing job before importing/using release credentials; and
3. immediately before immutable GitHub Release publication.

At every check, fully dereference annotated tags and require the resulting commit to equal the exact validated source SHA.

If the ref is missing, moved, ambiguous, or cannot be resolved, fail closed. Do not publish assets and do not repair/move the tag automatically.

This is defense in depth against configuration drift and closes the validation-to-publication TOCTOU window as far as GitHub's non-transactional APIs permit.

## 3. GitHub Artifact digest is mandatory metadata

For the selected source artifact, the GitHub Actions Artifact API digest MUST be present and MUST match the canonical `sha256:<64 lowercase hex>` form. Missing, malformed, or algorithm-mismatched digest metadata is a validation failure.

The validator records the artifact ID and GitHub-provided digest in validator-generated metadata. The privileged job requires the same artifact identity/digest values in that metadata before consuming the validator-produced handoff.

The archive's own SHA-256 remains a separate required check and is recomputed after every handoff.

The design does not treat build-provided provenance as an independent authority for the GitHub Artifact digest: the build cannot know the final artifact ID/digest until upload completes.

## 4. Parse application metadata before the release Environment

After ZIP confinement and tar preflight, the secret-free validation job MUST inspect the application bundle without executing application code.

At minimum it verifies:

- exactly one expected `.app` bundle;
- `Info.plist` is a regular confined file;
- `CFBundleIdentifier` equals trusted publisher configuration;
- `CFBundleShortVersionString` / configured release version contract matches the version tag;
- `CFBundleExecutable` is a safe basename and resolves to the expected regular non-symlink executable inside `Contents/MacOS`;
- the bundle basename matches the configured application basename.

A portable implementation should parse plist data with a data parser (for example Python `plistlib`) rather than invoking any binary or script from the release artifact.

The privileged signing job repeats these checks after downloading the validator-produced artifact.

## 5. No implicit trust from `workflow_run`

`workflow_run` is only the transport/trigger mechanism. It is not itself proof that the input is releasable.

The secret-free validator still independently verifies:

- same repository ID/full name;
- exact canonical Release Build workflow ID/path;
- `push` event and successful conclusion;
- exact run ID and run attempt;
- exact source SHA;
- immutable version tag binding;
- one exact non-expired artifact;
- mandatory GitHub Artifact digest;
- strict provenance schema;
- archive SHA-256;
- archive member confinement;
- application metadata contract.

Only validator-generated outputs/artifacts may cross into the release Environment job.

## 6. Rollout gate

The implementation rollout is amended to require this order:

1. merge PR #3 release/archive hardening;
2. merge/import PR #4 repository governance;
3. verify the effective `refs/tags/v*` Ruleset blocks update and deletion;
4. implement and test the two-stage release path;
5. verify old-ancestor tags use current default-branch publisher code in a disposable/test repository;
6. verify tag-move attempts are rejected by the effective Ruleset;
7. only then enable the two-stage publisher as the production template path;
8. remove the obsolete tag-selected privileged path.

## 7. Added acceptance tests

Implementation must additionally cover:

- missing GitHub Artifact digest rejected;
- malformed/non-SHA256 Artifact digest rejected;
- Info.plist bundle ID mismatch rejected before the release Environment;
- bundle version/tag mismatch rejected before the release Environment;
- unsafe or symlinked `CFBundleExecutable` rejected before the release Environment;
- tag binding rechecked in the privileged job;
- tag binding rechecked immediately before publication;
- production rollout documentation refuses enablement when the immutable `v*` Ruleset is not verified.

These amendments preserve the core design decision:

> Tag commit selects application bytes; current default branch selects privileged release-control code.

They strengthen it by making immutable tag governance and repeated ref binding explicit parts of the privileged release trust boundary.
