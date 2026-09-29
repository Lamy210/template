from __future__ import annotations

import re


REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def is_canonical_repository_name(value: object) -> bool:
    if not isinstance(value, str) or REPOSITORY_RE.fullmatch(value) is None:
        return False

    owner, name = value.split("/", 1)
    return owner not in {".", ".."} and name not in {".", ".."}
