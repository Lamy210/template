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
- branch is current with `main` before merge
- all review conversations are resolved
- no force push to `main`
- no direct push to `main`
- linear history

## Solo OSS profile

For repositories with one maintainer:

- require a PR
- require zero approvals
- require all status checks
- block direct/force pushes
- allow maintainer merge after checks pass

Do not require one approval when the repository has only one maintainer; that creates a self-approval deadlock.

## Team OSS profile

For repositories with multiple maintainers:

- require a PR
- require at least one approval
- dismiss stale approvals after relevant code changes
- require CODEOWNERS review for security/release-sensitive paths
- require all status checks
- block direct/force pushes

## Rulesets

Recommended `main` Ruleset:

1. Restrict deletion.
2. Block force pushes.
3. Require a pull request before merging.
4. Require status checks.
5. Require conversation resolution.
6. Require linear history.
7. Require the branch to be up to date before merging when merge queue is unavailable.
8. Keep bypass permissions minimal.

Recommended `v*` tag Ruleset:

- restrict tag deletion
- restrict tag updates
- allow creation only by maintainers/release automation

Published tags are immutable. If `v1.2.0` is wrong, publish `v1.2.1`; never move `v1.2.0` to a different commit.

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
