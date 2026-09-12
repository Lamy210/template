# Coding Standards

This document defines the default coding rules for repositories created from this template. Tool configuration is the executable form of this policy; when this document and CI disagree, fix the inconsistency instead of bypassing CI.

## 1. General principles

Code should optimize for correctness, readability, testability, and safe change rather than cleverness.

- Keep one clear responsibility per type, function, workflow, and script.
- Prefer explicit data flow and dependencies over hidden global state.
- Prefer small composable units over large multipurpose objects.
- Make invalid states difficult to represent.
- Fail with actionable errors at system boundaries.
- Keep security-sensitive behavior explicit and reviewable.
- Avoid suppressing warnings merely to make CI pass.

## 2. Formatting

Formatting is not subjective in this template.

- `.editorconfig` controls basic whitespace and newline conventions.
- Swift source is formatted by SwiftFormat using `.swiftformat`.
- CI runs SwiftFormat in lint mode and rejects formatting drift.
- Shell scripts are formatted by `shfmt` and checked by ShellCheck.

Do not hand-format code against the configured formatter. Change the shared formatter configuration only in a dedicated, reviewed change.

## 3. Swift naming and structure

Follow Swift API design conventions and the configured SwiftLint rules.

- Types use `UpperCamelCase`.
- Functions, variables, properties, and enum cases use `lowerCamelCase`.
- Boolean names should read as predicates where practical, such as `isEnabled`, `hasPermission`, or `canRetry`.
- Avoid abbreviations unless they are established domain terms.
- Prefer names that describe intent rather than implementation details.
- Keep a file focused on one primary type or tightly related extensions.
- Use extensions to separate meaningful protocol conformances or concerns, not to hide oversized types.

## 4. Access control and mutability

Use the narrowest access level that satisfies the design.

- Prefer `private` or `fileprivate` implementation details over unnecessary `internal` exposure.
- Expose `public` API deliberately and document compatibility implications.
- Prefer `let` over `var` when mutation is not required.
- Prefer value types when identity and shared mutable state are unnecessary.
- Avoid process-wide mutable singleton state unless the dependency is explicitly isolated behind an interface.

## 5. Functions and complexity

Complexity is a merge gate, not merely a review suggestion. The root `.swiftlint.yml` defines the executable thresholds.

| Metric | Warning / CI gate | Hard error |
| --- | ---: | ---: |
| Cyclomatic complexity | 12 | 20 |
| Function body length | 60 lines | 100 lines |
| Closure body length | 40 lines | 80 lines |
| Type body length | 300 lines | 500 lines |
| File length | 500 lines | 800 lines |
| Function parameters | 6 | 8 |
| Tuple members | 3 | 4 |
| Type nesting | 2 levels | warning-only rule |
| Function nesting | 2 levels | warning-only rule |

CI invokes SwiftLint with `--strict`, so warning thresholds are blocking in pull requests.

When a threshold is exceeded, prefer refactoring over raising the limit. Typical remedies include extracting a type, extracting a pure function, replacing branching with polymorphism/state modeling, grouping parameters into a value type, or separating orchestration from domain logic.

Threshold changes must be intentional policy changes and should not be hidden inside unrelated feature work.

## 6. Error handling

- Do not silently ignore failures that affect correctness, persistence, security, or user-visible behavior.
- Prefer typed errors or domain-specific error mapping at boundaries.
- Use `try?` only when failure is genuinely equivalent to absence and that intent is obvious.
- Avoid `fatalError` in recoverable production paths.
- Preserve useful underlying error context when wrapping errors.
- User-facing error messages and diagnostic logs have different audiences; do not leak secrets or internal credentials into either.

## 7. Optionals and unsafe operations

- Prefer early `guard` exits over deeply nested optional handling.
- Avoid forced casts and forced tries unless an invariant makes failure impossible and that invariant is locally obvious.
- Avoid force unwraps in normal production control flow; prefer explicit validation or modeled invariants.
- If an unsafe operation is unavoidable, keep the scope narrow and document why it cannot fail.

## 8. Concurrency

- Treat actor isolation and thread ownership as part of API design.
- UI state changes belong on the main actor when required by SwiftUI/AppKit semantics.
- Avoid detached tasks unless task-local context and cancellation behavior have been considered.
- Propagate cancellation where operations are cancellable.
- Do not protect shared mutable state with ad-hoc assumptions about call order.
- Prefer structured concurrency and actors over manually shared mutable state.

Concurrency changes require tests for cancellation, ordering, duplicate execution, or races when those behaviors are relevant.

## 9. SwiftUI and AppKit boundaries

- Keep view bodies declarative; move non-trivial business logic out of views.
- Do not use views as persistence, networking, or release-service containers.
- Keep AppKit bridging code isolated behind narrow adapters.
- Keep side effects at explicit boundaries so domain logic remains testable.
- Avoid oversized observable/view-model objects that become application-wide service locators.

## 10. Dependencies

- Add a dependency only when it meaningfully reduces risk or maintenance cost.
- Prefer platform APIs for small, stable functionality.
- Pin and update CI dependencies deliberately.
- Review dependency licenses, maintenance state, and security impact for production dependencies.
- Do not introduce a package solely to avoid writing a small, well-tested local abstraction.

## 11. Tests

Behavior changes require tests at the lowest useful level.

- Unit tests cover deterministic domain behavior and edge cases.
- Integration tests cover boundaries such as filesystem, networking, persistence, process execution, or platform adapters.
- UI tests are reserved for critical user flows where lower-level tests cannot provide equivalent confidence.
- A bug fix should include a regression test whenever the behavior is testable.
- Tests should verify observable behavior rather than implementation details.

Avoid tests whose primary purpose is increasing coverage percentage without protecting behavior.

## 12. Comments and documentation

Comments explain **why**, constraints, invariants, security assumptions, or non-obvious trade-offs. They should not narrate straightforward code.

SwiftLint's default `todo` rule is active and CI runs in strict mode. Do not leave untracked `TODO`/`FIXME` markers in merged production code. Prefer a GitHub issue and reference it in a narrowly scoped comment when future work must remain visible in source.

Public API or complex internal protocols should document behavior, ownership, errors, concurrency expectations, and lifecycle where those are not obvious from the signature.

## 13. Logging and sensitive data

- Never log passwords, tokens, private keys, raw authorization headers, or signing material.
- Avoid logging personal/user content unless it is explicitly required and reviewed.
- Prefer structured metadata over concatenated free-form diagnostic strings.
- Keep release CI logs useful without exposing credential values.

## 14. SwiftLint suppressions

A suppression is an exception to policy and should be rare.

Preferred order:

1. fix the violation;
2. refactor the code;
3. use the narrowest possible `swiftlint:disable:this`, `:next`, or `:previous` suppression;
4. document why the exception is safe.

Do not use `swiftlint:disable all`. Do not disable a rule globally just because one call site is inconvenient. SwiftLint's blanket/superfluous disable checks remain enabled to catch broad or unnecessary suppressions.

## 15. Shell and release automation

Shell scripts in this repository are production code.

- Start Bash scripts with `set -euo pipefail` unless there is a documented reason not to.
- Quote variable expansions unless intentional word splitting is required.
- Validate untrusted or externally supplied paths and identifiers before use.
- Use temporary directories/files with restrictive permissions for sensitive material.
- Ensure cleanup occurs on failure as well as success.
- Keep signing and notarization secrets out of build/test jobs.

ShellCheck and `shfmt` are required CI gates.

## 16. GitHub Actions

- Default `GITHUB_TOKEN` permissions to read-only and grant write scopes per job.
- Pin third-party actions to full commit SHAs.
- Set job timeouts.
- Use `persist-credentials: false` for checkout when Git credentials are unnecessary.
- Do not use `pull_request_target` to execute untrusted pull-request code.
- Do not pass privileged secrets wholesale with `secrets: inherit`.
- Put expression-derived user-controlled values into environment variables before using them in shell scripts.

`actionlint` and `zizmor` enforce a portion of this policy automatically.

## 17. Exceptions and policy changes

A policy exception must be narrower than the rule it relaxes. A repository-wide rule or threshold change should include:

- the concrete problem with the existing rule;
- examples demonstrating the false positive or unreasonable cost;
- the proposed replacement policy;
- the expected impact on existing code;
- CI evidence showing the new configuration is valid.

Do not combine a policy relaxation with the feature that needs the relaxation unless the coupling is unavoidable and explicitly reviewed.
