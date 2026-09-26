# Test Policy Profiles

Named test profiles provide a small, stable adoption interface over the existing low-level `MACOS_*` test variables. Profiles do not replace the low-level interface: they provide defaults, explicit repository variables override those defaults independently, and `classify-test-policy.py` remains the final semantic invariant checker.

## Profiles

Set both `MACOS_TEST_PROFILE` and `MACOS_TEST_ADAPTER`.

| Profile | Adapter | Integration | Coverage | E2E | Visual |
| --- | --- | --- | --- | --- | --- |
| `minimal` | `swiftpm` or `xcode` | disabled | disabled | disabled | disabled |
| `standard` | `swiftpm` or `xcode` | disabled | enabled + required | disabled | disabled |
| `macos-app` | `xcode` | disabled | enabled + required | enabled + required | disabled |
| `macos-ui-strict` | `xcode` | disabled | enabled + required | enabled + required | enabled + required |

All profiles default `MACOS_VISUAL_BOOTSTRAP` to false. Enabling bootstrap is always an explicit repository decision.

Recommended SwiftPM baseline:

```text
MACOS_TEST_PROFILE=standard
MACOS_TEST_ADAPTER=swiftpm
```

Recommended macOS application baseline:

```text
MACOS_TEST_PROFILE=macos-app
MACOS_TEST_ADAPTER=xcode
```

## Independent overrides

Existing low-level variables override one profile field at a time. The resolver never silently changes a second field to repair an invalid combination.

For example, this keeps E2E enabled but makes it optional:

```text
MACOS_TEST_PROFILE=macos-app
MACOS_TEST_ADAPTER=xcode
MACOS_E2E_REQUIRED=false
```

By contrast, this is intentionally invalid:

```text
MACOS_TEST_PROFILE=macos-app
MACOS_TEST_ADAPTER=xcode
MACOS_E2E_ENABLED=false
```

The `macos-app` profile still contributes `E2E_REQUIRED=true`. Because required-while-disabled is invalid, the classifier fails closed. To disable E2E completely, explicitly override both fields:

```text
MACOS_E2E_ENABLED=false
MACOS_E2E_REQUIRED=false
```

The same independent-override rule applies to Integration, Coverage, Visual, and Visual bootstrap. Profiles never bypass classifier invariants such as Visual requiring E2E or macOS E2E requiring the Xcode adapter.

## Legacy mode

Leave `MACOS_TEST_PROFILE` empty to preserve the original low-level configuration contract.

Legacy defaults are unchanged:

- an empty `MACOS_TEST_ADAPTER` leaves the template explicitly unconfigured;
- Integration is disabled and optional unless explicitly configured;
- Coverage is disabled by default and becomes required when enabled unless `MACOS_COVERAGE_REQUIRED=false`;
- E2E is disabled and optional unless explicitly configured;
- Visual is disabled by default and becomes required when enabled unless `MACOS_VISUAL_REQUIRED=false`;
- Visual bootstrap is disabled unless explicitly enabled.

This means existing adopter repositories can merge the profile resolver without changing behavior.

## Low-level variables

The resolver reads these existing variables as independent overrides:

```text
MACOS_INTEGRATION_ENABLED
MACOS_INTEGRATION_REQUIRED
MACOS_COVERAGE_ENABLED
MACOS_COVERAGE_REQUIRED
MACOS_E2E_ENABLED
MACOS_E2E_REQUIRED
MACOS_VISUAL_ENABLED
MACOS_VISUAL_REQUIRED
MACOS_VISUAL_BOOTSTRAP
```

Boolean values accept only empty, `true`, or `false`. Any other non-empty value is a configuration error.

Application topology remains configured separately through variables such as:

```text
MACOS_TEST_WORKING_DIRECTORY
MACOS_TEST_PROJECT_PATH
MACOS_TEST_WORKSPACE_PATH
MACOS_TEST_SCHEME
MACOS_TEST_PLAN
MACOS_TEST_DESTINATION
MACOS_E2E_SCHEME
MACOS_E2E_TEST_PLAN
MACOS_VISUAL_MANIFEST_PATH
```

Profiles deliberately do not guess repository-specific Xcode projects, workspaces, schemes, plans, or Integration filters.

## Processing model

The `Tests` workflow uses this fixed pipeline:

```text
repository variables
  -> resolve-test-profile.py
  -> normalized low-level policy JSON
  -> classify-test-policy.py
  -> Unit / Integration / Coverage / E2E / Visual
  -> Tests / Required Gate
```

Unknown profile names, malformed boolean values, incompatible adapters, and invalid override combinations fail closed before test execution proceeds.

The template self-validates all four named profiles with committed adopter fixtures on GitHub-hosted runners. `minimal` and `standard` exercise the production SwiftPM path, `macos-app` exercises production Xcode unit/coverage/E2E paths, and `macos-ui-strict` adds the production Visual comparison path over the deterministic Xcode E2E capture artifact. The strict profile runtime check reuses the same Xcode unit/E2E results because its additional policy surface is Visual; it does not spend extra macOS jobs rerunning identical unit/E2E commands.

Profile adoption validation remains secret-free and read-only. It does not introduce repository writes or privileged release behavior.
