# GitHub Ruleset Governance

This template keeps its recommended repository Rulesets as reviewable desired-state JSON under `rulesets/`.

The files are **not** an automatic synchronization mechanism. Committing them does not change live GitHub Settings. A repository administrator must review and import the desired state deliberately.

## Desired-state files

- `rulesets/main-solo.json` — Solo OSS protection for the repository default branch.
- `rulesets/release-tags.json` — immutable release-tag policy for `refs/tags/v*`.

The Solo profile is intentionally portable and minimal:

- it uses `~DEFAULT_BRANCH` instead of a literal branch name;
- it stores no repository/ruleset IDs;
- it stores no user/team actor IDs;
- it stores no GitHub App integration ID;
- it stores no Administration credential;
- it intentionally omits optional import/export fields such as `source_type` from the canonical template shape, even though GitHub's official Ruleset recipes may include them;
- it excludes effective/runtime response fields such as `current_user_can_bypass`.

GitHub's official import recipes demonstrate both forms: some include `source_type: "Repository"` and some omit `source_type`. This template chooses omission as its canonical form so the source-controlled desired state stays minimal and repository-portable. Treat rejection of `source_type` here as a **template canonicalization rule**, not as a claim that GitHub itself does not support the field.

## Canonical Solo policy

The default-branch profile requires:

- pull requests before changes reach the default branch;
- zero required approvals for a one-maintainer repository;
- no path-specific `required_reviewers` approval requirement;
- no extra approval requirement for unattributed changes;
- stale review approvals are dismissed when new commits are pushed (`dismiss_stale_reviews_on_push=true`);
- all review conversations resolved;
- squash as the allowed merge method in the Ruleset contract;
- linear history;
- deletion protection;
- non-fast-forward / force-push protection;
- `Required gate`;
- `swift-quality / Swift quality`;
- required status checks remain enforced when a matching ref is created; GitHub's `do_not_enforce_on_create` field may be omitted or explicitly `false`, but not `true`;
- portable status-check entries containing only the check context, not repository-specific `integration_id` values;
- no additional ref rules that can silently make the default branch un-updatable;
- no routine bypass actors.

The zero-approval value is deliberate. GitHub does not allow a PR author to satisfy their own required approval, so requiring one approval in a one-maintainer repository creates a merge deadlock.

## Canonical release-tag policy

The release-tag profile targets:

```text
refs/tags/v*
```

It allows creation of a new matching tag but restricts subsequent update and deletion. The operational contract is:

> Once a release tag exists, do not move or delete it. Publish a new version instead.

The portable profile intentionally contains only the `update` and `deletion` restrictions. In particular, it does not add a `creation` restriction, because with no bypass actors that would prevent the normal release flow from creating a new matching version tag.

Do not test this policy by creating a production-looking throwaway tag in this repository. A correctly immutable tag may intentionally be impossible to clean up afterward. Use GitHub Rule Insights/effective-rule inspection here; use a disposable test repository for destructive tag-rule testing.

### Disposable runtime proof for immutable release tags

After importing the release-tag Ruleset into a **disposable repository**, run the destructive proof tool with two distinct existing commits:

```bash
bash scripts/ci/prove-release-tag-immutability.sh \
  --repository owner/disposable-ruleset-proof \
  --confirm-disposable owner/disposable-ruleset-proof \
  --tag v0.0.1 \
  --initial-sha <older-or-first-test-commit-sha> \
  --move-sha <different-test-commit-sha>
```

The command proves the three required runtime behaviors in order:

1. creation of a new canonical `vX.Y.Z` tag succeeds;
2. moving that exact tag to the second commit is rejected, and a read-back still resolves the tag to the initial SHA;
3. deleting that exact tag is rejected, and a read-back proves the tag still exists at the initial SHA.

The script is deliberately destructive and fail-closed:

- `--confirm-disposable` must exactly repeat the target repository;
- it refuses to target `GITHUB_REPOSITORY` when that environment variable names the same repository;
- the tag must be canonical stable SemVer;
- both commit SHAs must be canonical, distinct 40-character lowercase hexadecimal values and must exist;
- the chosen tag must not already exist;
- if update or deletion unexpectedly succeeds, the proof fails immediately;
- a failed update/deletion counts as protection only when GitHub reports a repository-rule violation; authentication failures, permission failures, network/API errors, or other ambiguous failures fail the proof instead of being treated as immutability evidence.

With the correct immutable-tag Ruleset, the test tag cannot be cleaned up. That permanent test ref is expected in the disposable repository. Do not run this command against the production/template repository.

## Safe rollout

The repository has already consolidated the former governance and privileged-release branches into PR #3. The remaining landing sequence is therefore deliberately **PR #2 -> integrated PR #3 -> live policy rollout**.

PR #18 is only an integration preview of PR #2 plus the integrated PR #3 tree. It must not be merged.

### 1. Minimal administrative unblock

Open the currently active `main` repository Ruleset in GitHub Settings and change only:

```text
Required approving reviews: 1 -> 0
```

Do **not** add required status checks or a bypass actor in this emergency edit.

Why: PR #3 contains the stable `Required gate`, governance validation, and release-isolation checks that must exist successfully on `main` before they can safely become required live policy.

After saving, re-read the live Ruleset and confirm PR #2 is no longer blocked by the one-approval rule.

### 2. Merge PR #2 first

PR #2 is the consolidated macOS test/E2E/coverage/visual foundation and remains the first landing PR against `main`.

Before merging:

1. re-read the PR and require the exact expected head;
2. require every exact-head workflow to be successful;
3. require zero unresolved review threads;
4. squash-merge only.

After merge, wait for the resulting `main` workflows to complete successfully before touching PR #3.

### 3. Restack the integrated PR #3 from post-#2 main

PR #3 now contains all of the previously staged work:

- P0 release artifact handoff and the stable `Required gate`;
- source-controlled Ruleset governance and live-policy doctors;
- immutable release-tag rollout/proof tooling;
- privileged two-stage release isolation;
- protected `release` Environment audit/proof tooling;
- trusted release-run/tag/artifact identity binding;
- immutable GitHub Release publication;
- deterministic Homebrew automation-branch handling and strict checksum/Cask validation.

The old PR #4 and PR #6 branches were merged into PR #3 and must not be landed separately.

After PR #2 reaches `main`:

1. refresh/rebase PR #3 onto the resulting `main`;
2. stop on conflicts instead of silently preferring either side;
3. verify that the combined `.github/workflows/quality.yml` still contains both Ruleset-governance and release-isolation validation;
4. run fresh exact-head Quality, Swift Quality, and Release Isolation TDD;
5. require zero unresolved review threads.

### 4. Merge PR #3 (integrated)

Squash-merge PR #3 only after the post-#2 restack is clean and the fresh exact-head CI is successful.

After merge, wait for all default-branch workflows to complete successfully.

### 5. Observe actual main-branch check names

Do not infer required-check contexts from YAML display names.

Confirm GitHub actually emitted successful Check Runs on the merged `main` commit for:

```text
Required gate
swift-quality / Swift quality
```

If either context differs, stop. Update the desired-state JSON in a reviewed change before changing live Rulesets.

### 6. Import the Solo default-branch Ruleset

Import `rulesets/main-solo.json` only after the successful main-branch check names above have been observed.

Before enabling it, verify:

- target is only `~DEFAULT_BRANCH`;
- required approvals are `0`;
- no path-specific required reviewers exist;
- stale approvals are dismissed on push;
- conversation resolution is enabled;
- linear history is enabled;
- only squash is allowed by the Ruleset contract;
- `Required gate` is required;
- `swift-quality / Swift quality` is required;
- required checks are enforced on ref creation;
- no broad `release**` branch patterns exist;
- no bypass actors were introduced.

### 7. Disable or replace the legacy broad branch Ruleset

GitHub combines overlapping Rulesets. The existing legacy Ruleset currently targets the default branch and broad `release**` patterns and requires one approval.

A newly imported approval=0 Ruleset does **not** override that policy. After verifying the new Solo profile, deliberately disable/delete or replace the legacy Ruleset so only the intended effective policy remains.

Run both live main doctors afterward:

```bash
bash scripts/ci/audit-live-main-ruleset.sh owner/repo
bash scripts/ci/audit-live-main-rules.sh owner/repo
```

Both must pass.

### 8. Import and prove the immutable release-tag Ruleset

Import `rulesets/release-tags.json` and verify it targets only:

```text
refs/tags/v*
```

Then require all three assurance layers:

1. offline canonical validation;
2. `audit-live-release-tag-ruleset.sh`;
3. the disposable-repository creation/update/deletion runtime proof.

Do not run the destructive tag proof against the production/template repository.

### 9. Configure and prove the protected release Environment

Before enabling the privileged publisher:

1. configure the protected `release` Environment exactly as documented in `docs/RELEASE.md` and `docs/SECRETS.md`;
2. keep Apple signing/notarization credentials in Environment secrets, not broad repository secrets;
3. run the read-only Environment doctor;
4. run the disposable negative runtime proof and require:
   - the authorized default-branch control can enter the Environment;
   - unauthorized branch/tag refs cannot enter it.

A failed API call or permission error is not proof of policy enforcement.

### 10. Prove the post-split publisher boundary

Run the documented disposable/adopter post-split runtime proof.

Require evidence that a release tag pointing at a post-split trusted ancestor still uses the **current default-branch publisher control code**, rather than privileged code selected from the tag commit.

Do not enable production signing/publication until this proof succeeds.

### 11. Final smoke verification

Open a harmless pull request and verify:

1. `Required gate` is created;
2. `swift-quality / Swift quality` is created;
3. failing required checks block merge;
4. green required checks allow the Solo maintainer to merge without an external approval;
5. unresolved review conversations block merge;
6. squash is the supported merge path;
7. direct/force updates to the default branch remain restricted.

Also run the manual **Governance Audit** workflow and require it to pass.

## Read-only live main Ruleset doctor

After importing the reviewed Solo profile, audit the repository-owned Ruleset configuration itself:

```bash
bash scripts/ci/audit-live-main-ruleset.sh owner/repo
```

This doctor is read-only and complements, rather than replaces, the effective-rules doctor below. It requires exactly one active repository-owned branch Ruleset named `Solo default branch` and validates that Ruleset against the checked-in Solo contract, including:

- target is `branch`;
- source is the expected repository;
- target scope is exactly `~DEFAULT_BRANCH` with no broad `release**` patterns;
- approval count is zero;
- required checks and merge method match the canonical profile;
- bypass actors are empty when GitHub exposes that field;
- when GitHub reports `current_user_can_bypass`, it must equal `never`.

The Ruleset configuration API and effective-rules API answer different questions. Configuration audit catches broad targeting and bypass metadata that are not represented in branch effective-rule entries; effective audit catches additional repository/organization Rulesets that also apply to the actual default branch. Require both to pass after rollout.

As with the tag doctor, GitHub may omit `bypass_actors` for a caller that cannot write the Ruleset. An omitted field is not proof that bypass actors do not exist; administrator UI/import review remains part of rollout.

## Read-only effective-main doctor

After importing/replacing the reviewed branch Ruleset, audit the rules that GitHub is **actually enforcing** on the repository default branch:

```bash
bash scripts/ci/audit-live-main-rules.sh owner/repo
```

The command is read-only. It resolves the repository default branch, calls GitHub's effective branch-rules API, and validates the resulting active policy against the Solo contract.

It detects operational drift that desired-state JSON validation alone cannot see, including:

- a legacy overlapping Ruleset that still requires one or more approvals;
- multiple active `pull_request` or `required_status_checks` rules applying to the default branch;
- missing linear-history, force-push, or deletion protection;
- missing/renamed required checks;
- disabled strict status checks;
- unresolved-conversation enforcement being disabled;
- merge/rebase being allowed when the Solo profile expects squash-only;
- unexpected effective rule types.

The effective-rules API includes active rules from every applicable level, including repository and organization Rulesets. This is why the doctor is preferable to checking only the newly imported Ruleset in isolation.

For a private repository, run it with a `gh` authentication context that can read repository metadata. Do not give the doctor Administration/write credentials merely to perform this audit.

This doctor covers the default-branch effective policy. Release-tag immutability still requires the separate disposable-repository/runtime proof described below; do not infer tag update/deletion behavior from a successful branch audit.

## Read-only live release-tag Ruleset doctor

After importing the reviewed immutable-tag profile, audit the live repository Ruleset object itself:

```bash
bash scripts/ci/audit-live-release-tag-ruleset.sh owner/repo
```

The doctor is read-only. It lists tag-targeting Rulesets and deliberately requires **exactly one active tag Ruleset overall**, which must be the repository-owned Ruleset named `Immutable release tags`. This conservative rule prevents an additional repository- or organization-level tag Ruleset from being silently ignored when GitHub cannot provide a branch-style effective-rules view for tags. The doctor then fetches that Ruleset by ID and verifies the live configuration against the checked-in contract:

- target is `tag`;
- enforcement is `active`;
- source is the expected repository;
- ref target is exactly `refs/tags/v*`;
- update protection is enabled with `update_allows_fetch_and_merge=false`;
- deletion protection is enabled;
- no creation or other unexpected tag rule is present;
- bypass actors are empty when GitHub exposes that field to the caller;
- when GitHub reports `current_user_can_bypass`, it must equal `never` for the audit caller.

GitHub documents that `bypass_actors` is returned by the Ruleset API only when the caller has write access to the Ruleset. The read-only doctor therefore validates an empty bypass list when the field is visible, but it does **not** treat an omitted field as proof that bypass actors do not exist. Separately, when GitHub returns `current_user_can_bypass`, the doctor requires `never`; this prevents a green audit from silently accepting that the audit actor itself has a bypass path. Verify bypass actors in the administrator Ruleset UI/import review as part of rollout.

The repository Ruleset API can list/filter tag-targeting Rulesets and fetch individual Rulesets, but GitHub's effective-rules endpoint is branch-oriented. For that reason release-tag assurance deliberately uses three complementary checks rather than claiming one read-only query proves everything:

1. offline canonical JSON validation;
2. this live Ruleset configuration audit;
3. the disposable-repository creation/update/deletion runtime proof.

Do not replace the disposable runtime proof with this configuration audit.

### Run the same audit from GitHub Actions

After `.github/workflows/governance-audit.yml` has landed on the repository default branch, operators can run **Governance Audit** manually from the Actions tab.

The workflow is intentionally `workflow_dispatch`-only. It does not run on pull requests, pushes, or schedules, and it grants only `contents: read`. Checkout credentials are not persisted. The audit uses the ephemeral `github.token` only for read-only GitHub API calls made by the main-Ruleset, effective-main, and release-tag doctors.

A failed manual run is actionable evidence of live-policy drift. For example, if a legacy overlapping Ruleset still requires one approval, the workflow should fail until that Ruleset is disabled/replaced. Do not weaken the checked-in Solo profile or the auditor merely to make this workflow green.

The workflow is a verification surface, not an administration surface: it never imports, updates, disables, or deletes Rulesets.

## Smoke verification after import

Open a harmless pull request and verify:

1. `Required gate` is created.
2. `swift-quality / Swift quality` is created.
3. A failing required check blocks merge.
4. Green required checks allow the Solo maintainer to merge without an external approval.
5. An unresolved review conversation blocks merge.
6. The supported merge path is squash.
7. Direct/force updates to the default branch remain restricted.

Do not use a real release tag for destructive Ruleset testing.

## Offline validation

Run the same policy suites that Quality executes:

```bash
python3 -m unittest \
  scripts.ci.test_validate_rulesets \
  scripts.ci.test_validate_rulesets_portability \
  -v
python3 scripts/ci/validate_rulesets.py
```

After live import, additionally run:

```bash
bash scripts/ci/audit-live-main-ruleset.sh owner/repo
bash scripts/ci/audit-live-main-rules.sh owner/repo
bash scripts/ci/audit-live-release-tag-ruleset.sh owner/repo
```

Once the manual workflow is present on the default branch, run **Actions → Governance Audit → Run workflow** as the hosted equivalent and require it to pass before treating the live default-branch policy as verified.

The validator rejects policy weakening, noncanonical state, or lockout regressions such as:

- approval count becoming non-zero;
- path-specific `required_reviewers` being added to the Solo profile;
- an extra approval requirement for unattributed changes being enabled;
- `dismiss_stale_reviews_on_push` being missing, non-boolean, or `false`;
- `release*` branches being added to the default-branch profile;
- either canonical required check being removed or renamed;
- duplicate or non-string required check contexts;
- `do_not_enforce_on_create=true`, which would skip required status checks when a matching ref is created;
- repository-specific `integration_id` or other fields being added to the portable status-check entries;
- strict status-check policy being disabled;
- review-thread resolution being disabled;
- merge/rebase being added to the Solo merge methods;
- linear-history protection being removed;
- unexpected default-branch rule types such as an `update` restriction being added;
- bypass actors being added;
- effective/runtime response fields or template-noncanonical optional export fields being committed into canonical desired state;
- release-tag update/deletion protection being removed;
- a release-tag `creation` rule or another unexpected tag rule being added.

The validator is intentionally offline and secret-free. It does not call GitHub and does not mutate repository Settings.

## Recovery

### Repository is blocked after a Ruleset edit

Use an administrator account to open GitHub Settings -> Rulesets and disable or edit the offending live Ruleset.

Recovery does not depend on a CI-held Administration token or permanent bypass actor.

### A required check was renamed

Do not guess the new context name.

1. Run the workflow successfully without making the guessed context mandatory.
2. Observe the actual Check Run name GitHub emitted.
3. Update `rulesets/main-solo.json` in a reviewed pull request.
4. Run offline validation.
5. Update/import the live Ruleset only after the desired-state change is reviewed.

### A legacy Ruleset still blocks merge

Inspect every Ruleset applying to the ref. GitHub layers overlapping Rulesets, so the effective policy may come from an older rule even when the newly imported file looks correct.

Disable or replace obsolete overlapping Rulesets deliberately.

### Desired state and live state differ

Treat Git as the intended policy and GitHub Settings as the enforced policy. A mismatch is drift, not proof that either side changed automatically.

The first-phase template does not reconcile drift automatically. Review the difference, then either:

- update Git if the policy change was intentional; or
- update GitHub Settings/import the reviewed desired state if live configuration drifted unintentionally.

## Security constraints

Never add the following merely to automate Ruleset import:

- a broad personal access token in PR CI;
- a repository Administration token exposed to fork pull requests;
- `pull_request_target` that executes untrusted fork code;
- a permanent bypass actor used for routine merges.

A future bootstrap/doctor tool may use a narrowly scoped administrator credential outside untrusted PR execution, but that is not part of this phase.
