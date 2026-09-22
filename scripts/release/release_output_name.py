from __future__ import annotations

import re


DMG_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.dmg$")


def validate_dmg_name(value: object) -> list[str]:
    if not isinstance(value, str) or DMG_NAME_RE.fullmatch(value) is None:
        return ["DMG name must be a safe literal .dmg basename"]
    return []
