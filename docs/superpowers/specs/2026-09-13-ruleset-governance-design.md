# Repository Ruleset Governance Design

Date: 2026-09-13
Status: Ready for review

## 1. Purpose

Define a reusable, source-controlled GitHub Ruleset governance model for repositories generated from this template.

The first target is the Solo OSS profile used by `Lamy210/template`: one maintainer, pull-request-only changes to the default branch, stable required CI checks, immutable release tags, no routine bypass path, and no self-approval deadlock.

The design intentionally separates **desired state stored in Git** from **live repository administration state**. The repository can validate and review the desired configuration without storing an administration token in CI. A repository administrator imports the reviewed JSON into GitHub Settings.

## 2. Current observed repository state

As of 2026-09-13, the repository has one active branch ruleset named `main`.

Observed live properties:

- target: `branch`;
- includes `~DEFAULT_BRANCH` plus `refs/heads/release**`, `refs/heads/release/**/*`, and `refs/heads/release-*`;
- required approving review count: `1`;
- review-thread resolution: disabled;
- required status checks: none;
- force pushes blocked through `non_fast_forward`;
- deletion restricted;
- merge methods allowed by the pull-request rule: merge, squash, and rebase;
- no bypass actors.

The approval rule is a confirmed operational blocker for the Solo OSS profile. A squash merge attempt for PR #3 with a green head was rejected by GitHub because one approving review from a writer is required. The PR author cannot satisfy their own required approval.

The current ruleset ID and timestamps are runtime metadata only and MUST NOT be committed as desired-state identifiers.

## 3. Goals

The governance layer must:

1. make the intended Solo OSS repository rules reviewable in Git;
2. produce JSON that GitHub can import through Settings -> Rulesets -> Import a ruleset;
3. target only the default branch in the default branch profile;
4. remove the Solo self-approval deadlock by requiring zero approvals;
5. require stable check contexts that are created for every pull request;
6. require review-conversation resolution;
7. require linear history;
8. restrict deletion and force pushes on the default branch;
9. define immutable `v*` release-tag policy independently from branch policy;
10. prevent accidental weakening through repository CI validation;
11. avoid storing repository-administration credentials in ordinary CI;
12. support copying the governance files into repositories generated from this template.

## 4. Non-goals

The first implementation does not:

- automatically call the GitHub administration API;
- store a fine-grained PAT or GitHub App administration token in Actions;
- manage organization-level rulesets;
- manage GitHub Environments, Actions secrets, CodeQL, or repository merge settings automatically;
- create a Team OSS profile yet;
- grant routine bypass permissions;
- infer required status-check names from workflow display names;
- attempt to reconcile arbitrary third-party rulesets layered above repository rulesets.

A later bootstrap/doctor subsystem may expand into broader repository desired-state management after this smaller contract is proven.

## 5. Architecture

The governance source of truth is split into three layers:

```text
rulesets/
  main-solo.json          # importable default-branch desired state
  release-tags.json       # importable immutable release-tag desired state

scripts/ci/
  validate-rulesets.py    # offline semantic validator

docs/
  GITHUB_RULESETS.md      # operator import/rollout/recovery guide
```

The JSON files are directly importable GitHub Ruleset definitions. They contain only portable desired-state fields. Repository/runtime fields returned by GitHub such as `id`, `node_id`, `source`, `_links`, `created_at`, and `updated_at` are excluded.

`validate-rulesets.py` uses the Python standard library only. It validates both JSON syntax and template-specific policy invariants. The validator is an offline checker; it does not require GitHub credentials.

The existing Quality workflow runs the validator when `rulesets/**` or the validator itself changes. The workflow remains able to run without administration permissions.

## 6. Solo default-branch ruleset

Canonical file:

```text
rulesets/main-solo.json
```

### 6.1 Target

The branch condition MUST include only:

```json
"include": ["~DEFAULT_BRANCH"]
```

and MUST use an empty exclusion list in the template default profile.

Long-lived `release*` branches are deliberately excluded from this profile. If a future repository needs protected release branches, that repository adds a separate narrowly scoped profile instead of broadening the default ruleset.

### 6.2 Bypass

The Solo profile stores no bypass actors:

```json
"bypass_actors": []
```

This keeps bypass exceptional and administrator-mediated instead of making normal development depend on a bypass identity.

### 6.3 Pull-request rule

The desired pull-request rule requires:

- pull request before merging;
- `required_approving_review_count = 0`;
- `required_review_thread_resolution = true`;
- CODEOWNERS review not globally required in Solo mode;
- last-push approval not required;
- no beta path-specific required reviewers in the initial profile;
- squash as the only allowed PR merge method represented by the ruleset contract where GitHub accepts this parameter.

The zero-approval value is intentional: CI and conversation resolution remain blocking gates while avoiding the one-maintainer self-approval deadlock.

### 6.4 Required status checks

The first profile requires exactly these stable contexts:

```text
Required gate
swift-quality / Swift quality
```

The second name follows GitHub's reusable-workflow check naming convention: `<caller job> / <reusable job>`.

Required checks use the context name without an `integration_id` so the portable template does not embed repository-specific GitHub App IDs. A future stricter profile may pin an integration after repository bootstrap if the owning repository deliberately chooses that coupling.

The required-status-check rule uses:

```text
strict_required_status_checks_policy = true
```

for the initial foundation profile. Therefore the PR head must be tested against the latest base before merge. This matches the existing branching policy when merge queue is unavailable. Repositories that later decide CI cost outweighs strict update-before-merge semantics may introduce an explicit alternate profile rather than silently weakening this file.

### 6.5 History and ref mutation

The ruleset additionally requires:

- `required_linear_history`;
- `deletion` restriction;
- `non_fast_forward` protection.

These are independent of the pull-request rule and MUST remain present even if review parameters are changed later.

## 7. Release-tag ruleset

Canonical file:

```text
rulesets/release-tags.json
```

Target:

```text
refs/tags/v*
```

The release-tag ruleset is separate from branch protection so branch policy does not accidentally match release branches or vice versa.

The policy requires:

- tag creation remains possible for normal authorized release flows;
- updates to an existing matching tag are restricted through the `update` rule;
- deletion of matching tags is restricted through the `deletion` rule;
- no normal bypass actors are stored in the portable default profile.

The desired operational contract is: once `v1.2.3` exists, it is immutable. A bad release is corrected by publishing a new version, not by moving or deleting the old tag.

The template does not initially require signed tags because that would introduce a separate signing-key governance decision unrelated to the immediate P0 remediation.

## 8. Validator contract

`validate-rulesets.py` validates policy, not only JSON syntax.

It MUST fail when any of the following occurs.

### `main-solo.json`

- file is invalid JSON;
- `target != "branch"`;
- `enforcement != "active"`;
- `~DEFAULT_BRANCH` is not the sole include target;
- any `release*` branch pattern is present;
- bypass actors are non-empty;
- deletion restriction is missing;
- non-fast-forward protection is missing;
- required-linear-history rule is missing;
- pull-request rule is missing;
- approving review count is not zero;
- review-thread resolution is false or missing;
- merge methods contain anything other than squash when the field is present;
- required-status-check rule is missing;
- strict status-check policy is not true;
- required check contexts differ from the canonical set;
- duplicate rule types appear where the template contract expects one rule of that type;
- runtime-only GitHub fields such as `id`, `node_id`, `source`, `_links`, `created_at`, or `updated_at` are present at top level.

### `release-tags.json`

- `target != "tag"`;
- `enforcement != "active"`;
- include target is not exactly `refs/tags/v*`;
- bypass actors are non-empty;
- update restriction is missing;
- deletion restriction is missing;
- branch-only pull-request or required-status-check rules are present;
- runtime-only GitHub response metadata is present.

The validator produces precise file/rule diagnostics and a non-zero exit code. It does not mutate files.

## 9. CI integration

The existing Quality workflow remains the governance validation entry point.

A dedicated step runs:

```text
python3 scripts/ci/validate-rulesets.py
```

The step is intentionally cheap and secret-free.

No top-level workflow path filter is introduced solely for Ruleset files because the repository is moving toward stable required checks that must always be created. If later optimization is needed, applicability is decided inside an already-started required workflow.

The validator does not query live Rulesets during PR execution. Live drift detection requires administration/read semantics and layering awareness and belongs in a future doctor/manual audit command.

## 10. Safe rollout sequence

The rollout MUST avoid creating a repository lockout.

### Stage 0: confirmed current problem

PR #3 is green but cannot merge because the existing ruleset requires one approving review.

### Stage 1: minimal administrative unblock

An administrator edits the existing live `main` ruleset and changes only the Solo approval requirement:

```text
required approving reviews: 1 -> 0
```

Do not add new required checks in the same emergency edit.

Then verify PR #3 becomes mergeable.

### Stage 2: merge P0 CI foundation

Merge PR #3 first.

After the main-branch run completes, confirm GitHub emitted the stable contexts:

```text
Required gate
swift-quality / Swift quality
```

This order avoids importing a required check whose implementation has not yet landed on the default branch.

### Stage 3: review governance implementation

Merge the Ruleset governance PR containing the importable JSON, validator, and operator documentation.

The repository files now define the desired state but still do not claim live Settings are synchronized.

### Stage 4: import desired Rulesets

In GitHub Settings:

1. open Rulesets;
2. import `rulesets/main-solo.json`;
3. review the imported target and check contexts before creating it;
4. replace/disable the legacy overlapping branch ruleset so two conflicting branch policies do not layer accidentally;
5. import `rulesets/release-tags.json`;
6. inspect Rule Insights and the effective rules on `main` and a test `v*` ref.

GitHub aggregates overlapping rulesets and applies the most restrictive result. Therefore leaving the old approval=1 ruleset active would preserve the deadlock even if the new Solo ruleset requires zero approvals.

### Stage 5: functional smoke PR

Open a trivial PR and confirm:

- both required contexts are created;
- failed required CI blocks merge;
- green required CI allows merge without an external approval;
- unresolved review threads block merge when present;
- squash is the supported merge path;
- direct/force update of the default branch remains restricted.

Release-tag immutability should be verified without damaging a real release tag. Use a deliberately disposable `v0.0.0-ruleset-smoke` style ref only if the configured pattern deliberately includes it, or inspect Rule Insights/effective rules instead. Do not create a production-looking version merely for testing unless the repository release policy explicitly permits it.

## 11. Failure and recovery model

### Invalid JSON or policy weakening

CI fails before merge with an offline validation error.

### Required context renamed

A workflow/job rename changes the check context. The Ruleset JSON MUST NOT be updated by guesswork. First observe the new successful Check Run name in GitHub, then update the desired-state file in a reviewed PR, then change the live Ruleset.

### Accidental live lockout

An administrator uses GitHub Settings to disable or edit the offending live ruleset. Recovery does not depend on a CI-held bypass credential.

### Layered legacy rule conflict

Inspect all active rulesets applying to the ref. Because GitHub layers rulesets and uses the most restrictive overlapping result, the migration must disable or replace obsolete overlapping policies rather than assuming a new weaker setting overrides them.

### Import format changes upstream

The portable JSON follows GitHub's documented repository-ruleset body/import shape. The validator owns template-specific invariants only; it is not a full frozen clone of GitHub's API schema. If GitHub changes import syntax, update the JSON fixtures and validator together in a reviewed PR.

## 12. Security model

- no repository Administration token in PR CI;
- no `pull_request_target` execution for governance validation;
- desired-state files are ordinary reviewed source;
- no routine bypass actors;
- required check names are explicit and reviewed;
- import remains an administrator action;
- live state must never be claimed synchronized merely because JSON files exist;
- runtime IDs returned by GitHub are not portable configuration and are not committed.

A future automation profile may use a narrowly scoped GitHub App or fine-grained token with repository Administration write permission, but that is explicitly outside this first phase.

## 13. Testing strategy

Implementation follows TDD.

First write validator tests/fixtures that intentionally contain:

- approval count 1;
- extra release branch target;
- missing required check;
- wrong reusable-workflow context;
- strict status checks disabled;
- conversation resolution disabled;
- merge/rebase allowed;
- non-empty bypass actors;
- missing linear-history protection;
- mutable `v*` tags;
- leaked runtime GitHub metadata.

Each invalid fixture must fail for the expected reason before the production validator is implemented.

Then add valid Solo branch and release-tag fixtures and require a zero exit status.

Finally wire the validator into Quality and verify repository hygiene, GitHub Actions security, secret scanning, and Ruleset validation together.

## 14. Template portability

The Solo JSON must avoid values tied to `Lamy210/template` except stable check context names that the template itself defines.

Portable fields include:

- `~DEFAULT_BRANCH` instead of literal `main`;
- no repository ID;
- no ruleset ID;
- no source owner/name;
- no GitHub App integration ID;
- no user/team actor IDs.

A generated repository can therefore import the same file after its copied workflows have emitted the same stable check names once.

If an adopter renames a required job, the adopter owns the corresponding desired-state change and must validate the new observed check name before import.

## 15. Future extensions

Explicit follow-up candidates:

- `main-team.json` with one-or-more approvals and CODEOWNERS policy;
- `scripts/template/doctor.sh` live drift checks;
- optional admin-token `apply-rulesets` workflow or CLI;
- repository merge-setting desired state;
- Environment protection desired state;
- CodeQL/Dependabot/security-feature checks;
- organization-level profiles;
- merge-queue profile with `merge_group` compatibility.

These are not required to close the current Solo governance P0.

## 16. Acceptance criteria

The first Ruleset governance implementation is complete when:

- `main-solo.json` and `release-tags.json` are importable reviewed desired-state files;
- the offline validator rejects every weakening listed in Section 8;
- Quality runs the validator without privileged credentials;
- the operator documentation explains import, layering, rollout, and recovery;
- the existing approval=1 deadlock is removed administratively before PR #3 merge;
- PR #3 lands before `Required gate` is made mandatory on `main`;
- after import, only the default branch is governed by the Solo branch ruleset;
- `Required gate` and `swift-quality / Swift quality` are required;
- unresolved review conversations block merge;
- zero external approvals are required in Solo mode;
- linear history, deletion protection, and non-fast-forward protection apply;
- matching `v*` tags cannot be updated or deleted after creation;
- no implementation or documentation claims that live GitHub Settings are synchronized unless they were actually verified after import.
