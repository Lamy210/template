# Code Quality Policy

## Quality model

A passing formatter is not equivalent to high-quality code. The standard pipeline evaluates several independent properties:

1. formatting consistency
2. coding-standard / static-analysis findings
3. complexity and maintainability metrics
4. compiler warnings
5. unit/integration test correctness
6. architecture and dependency boundaries
7. security findings
8. packaging/release verification

The detailed coding rules live in [`CODING_STANDARDS.md`](CODING_STANDARDS.md). Configuration files such as `.swiftformat` and `.swiftlint.yml` are the executable form of that policy.

## Swift defaults

Recommended tools:

- SwiftFormat — deterministic source formatting
- SwiftLint — style, correctness, metrics, and optional analyzer rules
- Swift compiler warnings — correctness and migration signals
- XCTest / Swift Testing — behavioral verification
- CodeQL — security-oriented static analysis where supported

CI uses check/lint modes and fails on drift. Local developer tooling may run auto-fix commands before commit, but CI never rewrites source to make a pull request pass.

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

## Swift quality workflow

`.github/workflows/swift-quality.yml` runs automatically when Swift source or Swift quality configuration changes. It calls `reusable-swift-quality.yml` and provides three separate gates so failures are easy to diagnose:

1. **SwiftFormat check** — formatting drift
2. **Swift complexity gate** — maintainability/size metrics
3. **SwiftLint conventions and correctness** — the complete configured lint rule set

If the template repository does not contain application Swift source yet, the reusable workflow creates a small temporary Swift file so `.swiftformat` and `.swiftlint.yml` are still exercised by CI. The fixture is deleted before the job exits.

### Complexity gate

The dedicated complexity gate runs only SwiftLint metric rules and invokes SwiftLint with `--strict`. This means the warning threshold is a blocking pull-request threshold.

| Rule | Warning / CI gate | Hard error |
| --- | ---: | ---: |
| `cyclomatic_complexity` | 12 | 20 |
| `function_body_length` | 60 | 100 |
| `closure_body_length` | 40 | 80 |
| `type_body_length` | 300 | 500 |
| `file_length` | 500 | 800 |
| `function_parameter_count` | 6 | 8 |
| `large_tuple` | 3 | 4 |
| `nesting` type level | 2 | warning-only rule |
| `nesting` function level | 2 | warning-only rule |

These are deliberately moderate defaults for a reusable template. New projects should treat them as upper bounds, not targets. Tighten them when a project has evidence that lower limits are practical.

Do not raise a threshold simply because a new feature exceeds it. First consider extracting a type/function, grouping parameters into a value object, removing branching, or separating orchestration from domain behavior.

### SwiftLint analyzer rules

`unused_declaration` and `unused_import` are analyzer rules. They do **not** run during ordinary `swiftlint lint` execution.

SwiftLint analysis requires a clean compiler log containing the relevant `swiftc` invocations. The reusable workflow therefore exposes the optional `analyzer_compiler_log_path` input. When supplied, it runs:

```bash
swiftlint analyze --strict --compiler-log-path <clean-build-log>
```

A caller should only enable this after producing a non-incremental clean build log in the same job/workspace. Analyzer rules are slower and can have project-specific false positives, so they are opt-in rather than a mandatory template gate.

## Repository hygiene

The template also checks the infrastructure around the application:

- `actionlint` for GitHub Actions syntax and expressions
- `zizmor` for GitHub Actions security issues
- ShellCheck for shell correctness
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

For existing applications that cannot adopt the default complexity limits immediately, prefer a measured migration or tool-supported baseline over globally disabling the metric rules. The desired direction is monotonic improvement.

## Required pull-request gates

For a Swift/macOS repository created from this template, require at least:

- Swift format check
- Swift complexity gate
- SwiftLint conventions/correctness
- unit tests
- application build
- Repository hygiene
- GitHub Actions security
- dependency review for public repositories when enabled

Recommended when applicable:

- SwiftLint analyzer rules
- integration tests
- UI tests for critical flows
- CodeQL
- coverage ratchet
- performance regression tests
- architecture/dependency rule checks

## Compiler warnings

A generic lint workflow cannot know how every Xcode/SPM/Tauri/Flutter project builds, so compiler-warning enforcement belongs in the application's build job.

For new Swift projects, prefer a zero-warning build and enable warnings-as-errors in CI where the project/toolchain supports it. Existing projects should use the same baseline/ratchet approach instead of permanently accepting new warnings.

## Suppression policy

Do not silence findings globally merely to make CI green. Prefer, in order:

1. fix the underlying issue
2. refactor the code
3. narrow an exception to the smallest scope
4. document why the exception is safe

Do not use blanket `swiftlint:disable all`. SwiftLint's default blanket/superfluous disable checks remain enabled and CI treats their warnings as failures.

## Review expectations

Review should cover more than formatting:

- behavior and edge cases
- responsibility boundaries
- complexity and maintainability
- error handling and recovery
- concurrency/thread-safety
- memory/resource lifetime
- accessibility and macOS conventions
- security/privacy implications
- backwards compatibility
- testability and observability

Release/security workflow changes deserve the same review rigor as application code because they can alter credential access and artifact integrity.
