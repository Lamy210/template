from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImmutableReleasesSetting:
    enabled: bool
    enforced_by_owner: bool


def validate_immutable_releases_setting(
    document: object,
) -> tuple[list[str], ImmutableReleasesSetting | None]:
    errors: list[str] = []

    if not isinstance(document, dict):
        return ["immutable releases response must be a JSON object"], None

    enabled = document.get("enabled")
    enforced_by_owner = document.get("enforced_by_owner")

    if enabled is not True:
        if type(enabled) is not bool:
            errors.append("immutable releases enabled flag must be boolean true")
        else:
            errors.append("immutable releases must be enabled")

    if type(enforced_by_owner) is not bool:
        errors.append("immutable releases enforced_by_owner flag must be boolean")

    if errors:
        return errors, None

    assert enabled is True
    assert isinstance(enforced_by_owner, bool)
    return (
        [],
        ImmutableReleasesSetting(
            enabled=True,
            enforced_by_owner=enforced_by_owner,
        ),
    )
