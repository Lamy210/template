# Test Profiles and Adoption Validation Design

**Status:** Approved

**Date:** 2026-09-16

## Context

The test stack now exposes a stable `Tests / Required Gate`, reusable Swift tests, deterministic macOS E2E capture, trusted Visual Regression, coverage ratcheting, optional-subsystem semantics, and runtime verification. The current caller is intentionally low-level: repositories configure `MACOS_TEST_ADAPTER` and individual `MACOS_*_ENABLED` / `MACOS_*_REQUIRED` variables directly. The template repository itself remains unconfigured, so normal CI proves the bootstrap state but does not prove a new adopter can enable the complete stack successfully.

The next phase should improve adoption without weakening the existing fail-closed policy model or duplicating workflows per profile.

## Goals

1. Add named test-policy presets that reduce repetitive repository-variable configuration.
2. Preserve the current `MACOS_*` configuration as the canonical low-level interface and backward-compatible escape hatch.
3. Keep `classify-test-policy.py` as the final invariant checker; profiles must never bypass it.
4. Add real adoption fixtures that execute the reusable workflows on GitHub-hosted runners.
5. Keep ordinary template CI inexpensive by running full adoption tests only when relevant files change or on explicit dispatch.
6. Make setup eventually approachable through a deterministic setup command without requiring that command for advanced users.

## Non-goals

- Profiles do not create GitHub Rulesets, Environments, Secrets, or repository variables remotely.
- Profiles do not alter release-security boundaries.
- Profiles do not automatically enable Integration tests because Integration plans/filters are repository-specific and may duplicate Unit execution.
- Profiles do not automatically enable Visual bootstrap.
- The first profile implementation does not replace the existing `MACOS_*` variables.
- Adoption fixtures are test assets, not production starter applications.

## Architecture

Add one normalization layer before the existing classifier:

```text
Repository Variables
        |
        v
resolve-test-profile.py
        |
        | normalized policy JSON
        v
classify-test-policy.py
        |
        v
Tests / Required Gate
```

`resolve-test-profile.py` supplies profile defaults and explicit overrides. `classify-test-policy.py` remains responsible for semantic validity such as required-while-disabled, Visual requiring E2E, and E2E/Visual requiring Xcode.

No workflow is duplicated for a profile. All profiles converge into the existing normalized policy contract.

## Profile contract

`MACOS_TEST_PROFILE` accepts exactly:

- empty: legacy configuration mode
- `minimal`
- `standard`
- `macos-app`
- `macos-ui-strict`

Unknown names fail closed.

All configured profiles require `MACOS_TEST_ADAPTER` to resolve to `swiftpm` or `xcode`. `macos-app` and `macos-ui-strict` additionally require `xcode`.

| Profile | Integration | Coverage | E2E | Visual |
| --- | --- | --- | --- | --- |
| `minimal` | disabled | disabled | disabled | disabled |
| `standard` | disabled | enabled + required | disabled | disabled |
| `macos-app` | disabled | enabled + required | enabled + required | disabled |
| `macos-ui-strict` | disabled | enabled + required | enabled + required | enabled + required |

Visual bootstrap is always `false` unless explicitly enabled by `MACOS_VISUAL_BOOTSTRAP=true`.

## Precedence and override semantics

The precedence order is:

1. profile defaults
2. explicitly configured existing `MACOS_*` variables
3. classifier validation

Overrides are independent. The resolver must not silently weaken another field to make an override valid.

Example:

```text
MACOS_TEST_PROFILE=macos-app
MACOS_E2E_REQUIRED=false
```

keeps E2E enabled but makes it optional.

By contrast:

```text
MACOS_TEST_PROFILE=macos-app
MACOS_E2E_ENABLED=false
```

leaves the profile's `E2E_REQUIRED=true` in place, so the classifier rejects the policy as required-while-disabled. A repository that wants E2E fully disabled must explicitly set both `MACOS_E2E_ENABLED=false` and `MACOS_E2E_REQUIRED=false`.

This is deliberate: an override must not cause hidden policy weakening.

## Legacy compatibility

When `MACOS_TEST_PROFILE` is empty, the resolver must reproduce the current environment semantics exactly:

- empty adapter remains an intentionally unconfigured template
- Integration required defaults to false
- Coverage required defaults to true when Coverage is enabled unless explicitly set false
- E2E required defaults to false
- Visual required defaults to true when Visual is enabled unless explicitly set false
- Visual bootstrap defaults to false

Existing repositories therefore receive no behavior change merely because the resolver is introduced.

## Resolver interface

Create `scripts/test/resolve-test-profile.py`.

It supports:

```text
--from-env
--input <json>
--output <json>
```

`--from-env` and `--input` are mutually exclusive. The output JSON contains exactly the existing classifier keys:

```json
{
  "adapter": "xcode",
  "integrationEnabled": false,
  "integrationRequired": false,
  "coverageEnabled": true,
  "coverageRequired": true,
  "e2eEnabled": true,
  "e2eRequired": true,
  "visualEnabled": false,
  "visualRequired": false,
  "visualBootstrap": false
}
```

Profile identity is diagnostic metadata, not part of the classifier input contract. The resolver prints a human-readable summary and writes only classifier-compatible JSON to `--output`.

Boolean repository-variable values accept only empty, `true`, or `false`. Any other non-empty value is a configuration error.

## Workflow wiring

In `.github/workflows/tests.yml`, the `classify` job gains a resolver step before the classifier:

1. checkout
2. resolve profile/environment into `${RUNNER_TEMP}/test-policy.json`
3. run `classify-test-policy.py --input ... --github-output "$GITHUB_OUTPUT"`

All downstream jobs continue to consume classifier outputs exactly as they do today. Application-specific path, project/workspace, scheme, plan, destination, artifact, threshold, and profile-ID variables remain unchanged.

## Adoption runtime validation

Add a specialized workflow, not a universal required check.

### SwiftPM fixture

A tiny committed package under `Tests/AdoptionFixtures/SwiftPM` validates:

- `minimal`: Unit succeeds, other subsystems are not applicable
- `standard`: Unit succeeds and Coverage executes with the expected policy
- explicit override behavior remains visible in normalized policy tests

### Xcode macOS fixture

A tiny committed macOS app project under `Tests/AdoptionFixtures/MacOSApp` validates:

- `macos-app`: Unit/Coverage/E2E policy and execution
- `macos-ui-strict`: E2E produces deterministic capture input and Visual executes against a fixture baseline/bootstrap scenario

The Xcode fixture is checked in as a deterministic fixture, including its `.xcodeproj`; CI must not install a project generator merely to construct the fixture.

The fixture should have minimal SwiftUI/AppKit surface area, deterministic text/content, no network, no secrets, no external packages, and no TCC-dependent behavior.

## Adoption workflow triggers

The adoption workflow runs on `workflow_dispatch` and pull requests that modify relevant files, including:

- `.github/workflows/tests.yml`
- reusable Swift/E2E/Visual workflows
- `scripts/test/**`
- `scripts/visual/**`
- adoption fixtures
- adoption workflow itself

It should not run for unrelated documentation-only changes.

## CI cost boundary

- Resolver/classifier unit tests run on Ubuntu.
- SwiftPM adoption may use the canonical macOS runner required by reusable Swift tests.
- Xcode E2E/Visual adoption uses the canonical macOS runner only when its fixture or relevant workflow contracts change.
- No scheduled adoption run is required initially; explicit dispatch is sufficient for periodic confidence checks.

## Setup UX phase

Only after profile and adoption runtime behavior are proven should a setup command be added.

The setup command is local-only. It reads repository/project information, asks or accepts flags for adapter/profile and application-specific Xcode values, then emits:

- a validated `.template/config.json` local configuration file or equivalent generated configuration artifact
- exact GitHub repository-variable commands/instructions
- a setup summary with remaining manual Ruleset/Environment/Secret steps

It must not require GitHub Administration credentials and must not mutate live Rulesets automatically.

The low-level variables remain documented so advanced users and automation can bypass the setup command.

## Security invariants

- No `pull_request_target`.
- No release secrets in adoption workflows.
- Default permissions remain read-only.
- Profiles cannot weaken classifier validation.
- Unknown profile names or malformed booleans fail closed.
- A profile override never implicitly changes another requiredness field.
- Visual baseline publication remains governed by the existing trusted-main rules; adoption fixtures must not publish a trusted production baseline.
- Setup tooling does not store secrets or Administration tokens.

## Rollout

Implementation is deliberately split into three post-stack PRs:

1. **Test Profiles** — resolver, unit tests, workflow wiring, docs.
2. **Adoption Runtime** — SwiftPM/Xcode fixtures and GitHub-hosted end-to-end profile verification.
3. **Setup UX** — local setup command based on the proven profile contract.

Do not begin these implementation PRs until the existing #2 -> #16 test stack has landed on `main` and post-landing CI is green. The design branch may exist earlier, but implementation must branch from the trusted post-#16 `main` state.

## Acceptance criteria

The feature set is complete when:

- legacy no-profile behavior is regression-tested byte-for-policy-equivalent at the classifier boundary
- all four named profiles resolve deterministically
- invalid profiles/booleans and incompatible adapters fail closed
- explicit overrides follow the documented independent precedence rules
- the stable Required Gate consumes profile-resolved policy without new profile-specific workflow branches
- SwiftPM adoption passes for `minimal` and `standard`
- Xcode adoption passes for `macos-app` and `macos-ui-strict`
- setup UX can reproduce a known-good adopter configuration without remote admin mutation
- documentation describes both profile-first and low-level manual configuration paths
