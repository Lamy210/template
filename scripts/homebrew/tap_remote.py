from __future__ import annotations

import re


REPOSITORY_COMPONENT = r"[A-Za-z0-9_.-]+"
HTTPS_CLONE_RE = re.compile(
    rf"^https://github\.com/({REPOSITORY_COMPONENT})/({REPOSITORY_COMPONENT})\.git$"
)
SSH_CLONE_RE = re.compile(
    rf"^git@github\.com:({REPOSITORY_COMPONENT})/({REPOSITORY_COMPONENT})\.git$"
)


def _validate_single_line(label: str, value: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, str) or not value:
        return [f"{label} must be a non-empty string"]
    if value != value.strip() or "\n" in value or "\r" in value:
        errors.append(f"{label} must be a single canonical line")
    return errors


def _canonical_repository(
    *,
    canonical_https_url: str,
    canonical_ssh_url: str,
) -> tuple[list[str], str | None]:
    errors: list[str] = []

    https_match = HTTPS_CLONE_RE.fullmatch(canonical_https_url)
    if https_match is None:
        errors.append(
            "canonical HTTPS URL must be an exact GitHub clone URL ending in .git"
        )

    ssh_match = SSH_CLONE_RE.fullmatch(canonical_ssh_url)
    if ssh_match is None:
        errors.append(
            "canonical SSH URL must be an exact git@github.com owner/repo clone URL"
        )

    if https_match is None or ssh_match is None:
        return errors, None

    https_owner, https_name = https_match.groups()
    ssh_owner, ssh_name = ssh_match.groups()
    for label, owner, name in (
        ("canonical HTTPS URL", https_owner, https_name),
        ("canonical SSH URL", ssh_owner, ssh_name),
    ):
        if owner in {".", ".."} or name in {".", ".."}:
            errors.append(f"{label} contains an invalid repository component")

    https_repository = f"{https_owner}/{https_name}"
    ssh_repository = f"{ssh_owner}/{ssh_name}"
    if https_repository.casefold() != ssh_repository.casefold():
        errors.append(
            "canonical HTTPS and SSH URLs must identify the same repository"
        )

    if errors:
        return errors, None
    return [], https_repository


def validate_tap_remote_urls(
    *,
    fetch_url: str,
    push_url: str,
    canonical_https_url: str,
    canonical_ssh_url: str,
) -> list[str]:
    errors: list[str] = []
    for label, value in (
        ("fetch URL", fetch_url),
        ("push URL", push_url),
        ("canonical HTTPS URL", canonical_https_url),
        ("canonical SSH URL", canonical_ssh_url),
    ):
        errors.extend(_validate_single_line(label, value))

    if errors:
        return errors

    canonical_errors, repository = _canonical_repository(
        canonical_https_url=canonical_https_url,
        canonical_ssh_url=canonical_ssh_url,
    )
    errors.extend(canonical_errors)
    if errors or repository is None:
        return errors

    https_web_url = canonical_https_url[: -len(".git")]
    allowed = {
        canonical_https_url.casefold(),
        https_web_url.casefold(),
        canonical_ssh_url.casefold(),
    }
    for label, value in (("fetch URL", fetch_url), ("push URL", push_url)):
        if value.casefold() not in allowed:
            errors.append(
                f"{label} is not bound to the canonical tap repository clone URL"
            )

    return errors
