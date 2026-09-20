from __future__ import annotations

import re


ARTIFACT_ID_RE = re.compile(r"^[1-9][0-9]*$")
BARE_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def normalize_uploaded_artifact_identity(
    raw_artifact_id: object,
    raw_artifact_digest: object,
) -> tuple[str, str]:
    if not isinstance(raw_artifact_id, str) or ARTIFACT_ID_RE.fullmatch(raw_artifact_id) is None:
        raise ValueError("artifact ID must be a positive canonical decimal integer")

    if not isinstance(raw_artifact_digest, str):
        raise ValueError("artifact digest must be a string")
    if BARE_SHA256_RE.fullmatch(raw_artifact_digest) is not None:
        digest = f"sha256:{raw_artifact_digest}"
    elif CANONICAL_SHA256_RE.fullmatch(raw_artifact_digest) is not None:
        digest = raw_artifact_digest
    else:
        raise ValueError("artifact digest must be SHA-256 in lowercase hexadecimal form")

    return raw_artifact_id, digest
