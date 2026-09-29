from __future__ import annotations

import re
from urllib.parse import urlparse

from scripts.common.repository_name import is_canonical_repository_name


_SCP_REMOTE_RE = re.compile(r"^git@github\.com:(.+)$", re.IGNORECASE)


def repository_from_github_remote(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("GitHub remote must be a non-empty string")
    if value != value.strip() or "\n" in value or "\r" in value:
        raise ValueError("GitHub remote must be one canonical line")

    scp_match = _SCP_REMOTE_RE.fullmatch(value)
    if scp_match is not None:
        path = scp_match.group(1)
    else:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "ssh"}:
            raise ValueError("GitHub remote must use https, ssh, or git@github.com form")
        if parsed.hostname is None or parsed.hostname.casefold() != "github.com":
            raise ValueError("GitHub remote host must be github.com")
        if parsed.params or parsed.query or parsed.fragment:
            raise ValueError("GitHub remote must not contain params, query, or fragment")
        if parsed.password is not None:
            raise ValueError("GitHub remote must not contain a password")
        if parsed.scheme == "https":
            if parsed.username is not None or parsed.port is not None:
                raise ValueError("GitHub HTTPS remote must not contain credentials or a port")
        else:
            if parsed.username != "git" or parsed.port not in {None, 22}:
                raise ValueError("GitHub SSH remote must use git@github.com with optional port 22")
        path = parsed.path.lstrip("/")

    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    if not is_canonical_repository_name(path):
        raise ValueError("GitHub remote does not resolve to canonical owner/repo")
    return path
