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

## Safe rollout

The order below is required. Do not import the desired branch Ruleset in one step over the current repository configuration. The current repository rollout is deliberately staged as **PR #2 → PR #3 → PR #4 → PR #6**; this governance guide must not skip the consolidated test foundation in PR #2.

### 1. Minimal administrative unblock

Open the currently active `main` repository Ruleset in GitHub Settings and change only:

```text
Required approving reviews: 1 -> 0
```

Do **not** add `Required gate` in this emergency edit.

Why: PR #3 contains the workflow that creates the stable repository-level `Required gate`. Requiring that check before PR #3 has landed on `main` can lock the repository.

After saving, confirm PR #2 is no longer blocked by the one-approval rule.

### 2. Merge PR #2 first

PR #2 is the consolidated macOS test/E2E/coverage/visual foundation and is the first landing PR against `main`.

Squash-merge PR #2 only after rechecking its exact head, review threads, and all exact-head workflows. After merge, wait for the resulting `main` workflows to finish successfully before touching PR #3.

### 3. Merge PR #3

Refresh/rebuild PR #3 from the post-PR-#2 `main` state, verify that its diff remains release-hardening-only, and rerun fresh CI.

PR #3 contains the P0 release-artifact handoff fix and stable repository-level required CI gate. Merge it only after the post-#2 restack is verified.

After merge, wait for the default-branch workflows to complete successfully.

### 4. Observe the actual main-branch check names

Do not infer check contexts from YAML display names.

Confirm GitHub actually emitted these successful Check Runs on the merged `main` commit:

```text
Required gate
swift-quality / Swift quality
```

If either context is different, stop. Update the desired-state JSON only after observing the real successful name.

### 5. Refresh the governance branch from current main

Update `feat/ruleset-governance` from the post-PR-#3 `main` state before making PR #4 review-ready.

Both PRs modify `.github/workflows/quality.yml`. Resolve that integration by preserving:

- PR #3's release-artifact package/round-trip jobs and final `Required gate`;
- PR #4's `Ruleset governance validation` step inside `Repository hygiene`.

Do not replace one side with the other wholesale. Re-run the combined Quality workflow after reconciliation.

### 6. Merge the governance implementation

The governance PR adds:

- the two desired-state JSON files;
- offline semantic validation;
- Quality integration;
- this operator guide.

Merging this PR still does **not** synchronize live Rulesets automatically.

### 7. Import the Solo default-branch Ruleset

In GitHub:

1. Open the repository.
2. Open **Settings**.
3. Under **Code and automation**, open **Rulesets** -> **Rulesets**.
4. Choose the Ruleset import action.
5. Import `rulesets/main-solo.json`.
6. Before creating/enabling it, verify:
   - target is the default branch only;
   - approval count is `0`;
   - no path-specific required reviewers were introduced;
   - stale approvals are dismissed when new commits are pushed;
   - conversation resolution is enabled;
   - linear history is enabled;
   - `Required gate` is required;
   - `swift-quality / Swift quality` is required;
   - status checks are not skipped on ref creation (`do_not_enforce_on_create` is absent or `false`);
   - no repository-specific status-check integration IDs were introduced;
   - no `release*` branch patterns are present;
   - no unexpected ref-mutation rules were introduced;
   - no bypass actors were introduced.

### 8. Disable or replace the overlapping legacy branch Ruleset

GitHub combines overlapping Rulesets. A newly imported approval=0 Ruleset does **not** override an older approval=1 Ruleset; the effective result remains the more restrictive policy.

Therefore disable/delete or deliberately replace the obsolete legacy `main` Ruleset after confirming the imported Solo profile is correct.

Do not leave both active unintentionally.

### 9. Import the release-tag Ruleset

Import `rulesets/release-tags.json` and verify it targets only:

```text
refs/tags/v*
```

Confirm the effective rule restricts update and deletion while still allowing creation of a new version tag through the authorized release flow. A `creation` restriction is not part of the portable Solo tag profile.

### 10. Inspect effective rules

Use GitHub Rulesets/Rule Insights to inspect the effective rules on the default branch and matching tags.

Verify no organization-level or repository-level overlapping Ruleset reintroduces:

- approval=1 for Solo mode;
- broad `release**` branch targeting;
- missing required CI;
- a bypass path not represented by the intended policy.

Only after these governance checks are effective should PR #6 be restacked from trusted `main` and the privileged two-stage release rollout continue.

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

### Run the same audit from GitHub Actions

After `.github/workflows/governance-audit.yml` has landed on the repository default branch, operators can run **Governance Audit** manually from the Actions tab.

The workflow is intentionally `workflow_dispatch`-only. It does not run on pull requests, pushes, or schedules, and it grants only `contents: read`. Checkout credentials are not persisted. The audit uses the ephemeral `github.token` only for read-only GitHub API calls made by `audit-live-main-rules.sh`.

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
bash scripts/ci/audit-live-main-rules.sh owner/repo
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
