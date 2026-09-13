# Branching and Merge Policy

## Default model

Use trunk-based development with `main` as the only long-lived development branch.

Short-lived branches:

- `feat/*` — product features
- `fix/*` — bug fixes
- `refactor/*` — behavior-preserving refactors
- `perf/*` — performance work
- `security/*` — security fixes
- `docs/*` — documentation
- `chore/*` — maintenance and CI changes

Avoid a permanent `develop` branch. Release state is represented by immutable SemVer tags, not by long-lived release branches.

## Pull requests

Every change to `main` should arrive through a pull request. Prefer squash merge so review/fixup commits do not become permanent mainline history.

Recommended PR requirements:

- all required CI checks pass
- Swift coding-standard and complexity gates pass when Swift is used
- application build/tests pass
- branch is current with `main` before merge
- all review conversations are resolved
- no force push to `main`
- no direct push to `main`
- linear history

The default coding expectations are defined in [`CODING_STANDARDS.md`](CODING_STANDARDS.md) and the executable quality policy in [`QUALITY.md`](QUALITY.md).

## Stable required checks

A required Ruleset should select checks that are created for every pull request. Do not require a workflow whose top-level trigger can disappear because of `paths:` filtering; GitHub can leave such a required context pending when the workflow is skipped.

The template's stable foundation contexts are:

- `Quality / Required gate`
- `Swift Quality / Swift quality`

`Quality / Required gate` aggregates repository hygiene, secret scanning, GitHub Actions security, and the real upload/download release-artifact permission round-trip. Individual internal jobs remain visible for diagnosis, but the Ruleset can depend on the stable aggregate context rather than a growing list of implementation-detail job names.

`Swift Quality` is started for every pull request and `main` push. Source detection occurs inside the reusable workflow, so repositories without application Swift sources still create and complete the required context instead of leaving it pending.

When application-specific build/test workflows are added, expose a similarly stable final gate rather than requiring path-filtered internal jobs directly.

## Solo OSS profile

For repositories with one maintainer:

- require a PR
- require **zero approvals**
- require `Quality / Required gate`
- require `Swift Quality / Swift quality`
- require all application-specific stable gates once present
- require review-conversation resolution
- require linear history
- block direct/force pushes
- allow maintainer merge after checks pass

Do not require one approval when the repository has only one maintainer; GitHub does not allow a PR author to satisfy their own required approval, so that configuration creates a merge deadlock.

## Team OSS profile

For repositories with multiple maintainers:

- require a PR
- require at least one approval
- dismiss stale approvals after relevant code changes
- require CODEOWNERS review for security/release-sensitive paths
- require all stable status checks
- require review-conversation resolution
- require linear history
- block direct/force pushes

## Rulesets

Recommended `main` Ruleset:

1. Target only the default branch (`main` for the template default profile).
2. Restrict deletion.
3. Block force pushes.
4. Require a pull request before merging.
5. Use zero approvals for Solo OSS, or one-or-more approvals for the Team profile.
6. Require `Quality / Required gate`.
7. Require `Swift Quality / Swift quality`.
8. Require conversation resolution.
9. Require linear history.
10. Require the branch to be up to date before merging when merge queue is unavailable.
11. Keep bypass permissions minimal.

Do not include `release**`, `release-*`, or `release/**/*` in the default branch Ruleset when using this trunk-only model. If a project intentionally introduces long-lived release branches later, add a separate documented profile with narrowly scoped patterns rather than broadening the default template implicitly.

For Swift projects, the required check is the always-created `Swift Quality / Swift quality` context. Select status-check names only after GitHub has emitted them successfully at least once; the names above are the observed contexts from this template's CI.

Recommended `v*` tag Ruleset:

- target release tags matching `v*`
- restrict tag deletion
- restrict tag updates/non-fast-forward changes
- allow creation only by maintainers/release automation according to the repository's release profile

Published tags are immutable. If `v1.2.0` is wrong, publish `v1.2.1`; never move `v1.2.0` to a different commit.

## Repository merge settings

The template's recommended merge policy is:

- squash merge: enabled
- merge commits: disabled
- rebase merge: disabled
- delete head branches after merge: enabled

These are repository settings, not properties of the workflow files. A template consumer should configure or import them during repository bootstrap and verify them with a future template doctor command.

## Merge queue

Treat merge queue as an optional organization profile. For personal-account public repositories, use strict required checks / update-before-merge instead. The workflows should remain compatible with adding `merge_group` later if the repository moves to an organization.

## Commit conventions

Conventional Commit-style prefixes are recommended:

- `feat:`
- `fix:`
- `refactor:`
- `perf:`
- `test:`
- `docs:`
- `ci:`
- `build:`
- `chore:`
- `security:`

The squash commit should describe the PR as a whole.
