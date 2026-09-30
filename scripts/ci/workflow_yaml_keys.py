from __future__ import annotations

import re


YAML_KEY_TOKEN = r'(?:[A-Za-z0-9_-]+|"[A-Za-z0-9_-]+"|\'[A-Za-z0-9_-]+\')'


def yaml_key_pattern(key: str) -> str:
    escaped = re.escape(key)
    return rf'(?:{escaped}|"{escaped}"|\'{escaped}\')'


def normalize_yaml_key(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
