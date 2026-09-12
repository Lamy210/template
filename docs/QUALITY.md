# Code Quality Policy

## Quality model

A passing formatter is not equivalent to high-quality code. The standard pipeline evaluates several independent properties:

1. formatting consistency
2. lint/static-analysis findings
3. compiler warnings
4. unit/integration test correctness
5. architecture and dependency boundaries
6. security findings
7. packaging/release verification

## Swift defaults

Recommended tools:

- SwiftFormat — deterministic source formatting
- SwiftLint — style, maintainability, and analyzer rules
- Swift compiler warnings — correctness and migration signals
- XCTest / Swift Testing — behavioral verification
- CodeQL — security-oriented static analysis where supported

CI should use check/lint modes and fail on drift. Local developer tooling may run auto-fix commands before commit.

### Tool reproducibility

The reusable Swift quality workflow does not run `brew install` against moving formula versions. `scripts/ci/install-swift-quality-tools.sh` downloads upstream release artifacts, verifies SHA-256, checks the reported tool versions, and then adds the verified binaries to `PATH`.

Current template pins:

- SwiftFormat `0.63.0`
- SwiftLint `0.65.1`

When upgrading either tool:

1. review upstream release notes and changed/default rules
2. update the version and upstream asset SHA-256 together
3. run format/lint against representative repositories
4. review any new violations instead of globally disabling the new rules
5. merge the tool bump as an explicit dependency/quality-policy change

This prevents a Homebrew update from silently changing CI behavior for an unchanged application commit.

## Repository hygiene

The template also checks the infrastructure around the application:

- `actionlint` for GitHub Actions syntax and expressions
- `zizmor` for GitHub Actions security issues
- `ShellCheck` for shell correctness
- `shfmt` for shell formatting
- Homebrew Cask renderer smoke/syntax validation
- Markdown linting may be enabled when documentation volume justifies it

## Baseline and ratchet

Existing repositories should not be forced to satisfy an arbitrary new numerical threshold immediately.

For metrics such as coverage, warnings, lint violations, complexity, or TODO counts:

1. record the current value as a baseline
2. reject regressions
3. lower the tolerated debt when the project improves
4. eventually converge toward the target policy

New repositories should start with a zero-warning / zero-new-violation baseline wherever practical.

## Suggested PR gates

Required:

- source formatting check
- SwiftLint
- unit tests
- application build
- actionlint
- zizmor
- ShellCheck/shfmt when shell files exist
- dependency review for public repositories

Recommended when applicable:

- integration tests
- UI tests for critical flows
- CodeQL
- coverage ratchet
- performance regression tests
- architecture/dependency rule checks

## Complexity defaults

The root `.swiftlint.yml` intentionally starts with moderate thresholds rather than extreme restrictions. Teams should tighten thresholds after measuring the actual codebase.

Do not silence findings globally merely to make CI green. Prefer, in order:

1. fix the underlying issue
2. refactor the code
3. narrow an exception to the smallest scope
4. document why the exception is safe

## Review expectations

Review should cover more than formatting:

- behavior and edge cases
- responsibility boundaries
- error handling and recovery
- concurrency/thread-safety
- memory/resource lifetime
- accessibility and macOS conventions
- security/privacy implications
- backwards compatibility
- testability and observability

Release/security workflow changes deserve the same review rigor as application code because they can alter credential access and artifact integrity.
