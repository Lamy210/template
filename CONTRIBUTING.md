# Contributing

Thanks for contributing. This repository is a reusable macOS development/release baseline, so changes to CI, signing, packaging, and policy can affect every project created from it.

## Before you start

Read:

- [`docs/CODING_STANDARDS.md`](docs/CODING_STANDARDS.md)
- [`docs/QUALITY.md`](docs/QUALITY.md)
- [`docs/BRANCHING.md`](docs/BRANCHING.md)
- [`docs/SECRETS.md`](docs/SECRETS.md) for release/security work

## Branches

Use short-lived branches from `main`:

- `feat/*` — features
- `fix/*` — bug fixes
- `refactor/*` — behavior-preserving refactors
- `perf/*` — performance work
- `security/*` — security changes
- `docs/*` — documentation
- `chore/*` — maintenance/CI/dependencies

Do not push feature work directly to `main`.

## Local quality checks

For Swift applications created from this template, install/use the pinned tooling described in `docs/QUALITY.md`, then run:

```bash
swiftformat --lint .
swiftlint lint --strict
```

The dedicated CI complexity gate also runs these SwiftLint metric rules:

```text
cyclomatic_complexity
function_body_length
closure_body_length
type_body_length
file_length
function_parameter_count
nesting
large_tuple
```

For repository automation, also run the relevant checks when available:

```bash
actionlint
shellcheck scripts/**/*.sh
shfmt -d -i 2 -ci scripts
```

CI remains the source of truth because it runs pinned versions and security checks.

## Tests

Behavior changes need tests at the lowest useful level. Bug fixes should include a regression test when the failure is reproducible in automation.

Release automation changes should include either a deterministic script-level test/smoke test or a clear verification path that does not require exposing production credentials to pull-request jobs.

## Pull requests

Keep pull requests focused. A PR should answer:

1. What problem is being solved?
2. Why is this approach appropriate?
3. What behavior or policy changes?
4. How was it tested?
5. Does it alter security, permissions, secrets, release artifacts, or compatibility?

All required checks must pass before merge. Resolve review conversations before merging.

Squash merge is preferred so `main` keeps one coherent commit per pull request.

## Coding-policy violations

Do not fix CI by broadly disabling rules or raising thresholds inside unrelated work. Preferred order:

1. fix the violation;
2. refactor the code;
3. add a narrow, documented exception;
4. change shared policy only in a dedicated policy change with rationale.

## Security-sensitive changes

Treat these paths as high risk:

- `.github/workflows/**`
- `.github/actions/**`
- `scripts/release/**`
- signing/notarization configuration
- entitlements
- credential handling
- Homebrew publication automation

Do not place real secrets in commits, examples, test fixtures, workflow outputs, screenshots, or logs.

Pull-request workflows must remain secret-free. Do not introduce a path where pull-request-controlled code executes in a job holding Developer ID, App Store Connect, or cross-repository write credentials.

## Dependency changes

When adding/upgrading a dependency:

- state why it is needed;
- prefer pinned/reproducible versions in CI;
- review release notes for behavior/security changes;
- verify license and maintenance status for application dependencies;
- run affected tests and quality gates.

## Commit messages

Use concise, intent-oriented messages. Conventional prefixes are recommended:

```text
feat:
fix:
refactor:
perf:
test:
docs:
ci:
security:
chore:
```

The final squash commit should describe the pull request as a whole.
