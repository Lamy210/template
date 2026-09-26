from __future__ import annotations


def _validate_single_line(label: str, value: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, str) or not value:
        return [f"{label} must be a non-empty string"]
    if value != value.strip() or "\n" in value or "\r" in value:
        errors.append(f"{label} must be a single canonical line")
    return errors


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

    https_base = canonical_https_url.rstrip("/")
    if not https_base.startswith("https://"):
        errors.append("canonical HTTPS URL must use https://")
    if canonical_ssh_url.startswith("-"):
        errors.append("canonical SSH URL must not be option-like")

    allowed = {
        https_base.casefold(),
        f"{https_base}.git".casefold(),
        canonical_ssh_url.casefold(),
    }
    for label, value in (("fetch URL", fetch_url), ("push URL", push_url)):
        if value.casefold() not in allowed:
            errors.append(
                f"{label} is not bound to the canonical tap repository clone URL"
            )

    return errors
