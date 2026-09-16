#!/usr/bin/env python3
"""Build a self-describing rolling visual baseline bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

CONTROLLED_KEYS = {
    "runnerFamily",
    "architecture",
    "xcodePolicy",
    "locale",
    "language",
    "timezone",
    "appearance",
    "displayScale",
    "captureGeometry",
    "fixtureVersion",
    "captureContractVersion",
    "comparatorSchemaVersion",
}
STRING_CONTROLLED_KEYS = CONTROLLED_KEYS - {
    "captureContractVersion",
    "comparatorSchemaVersion",
}
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
CASE_ID_RE = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_fingerprint(controlled: dict[str, Any]) -> str:
    encoded = json.dumps(
        controlled,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _validate_controlled_profile(controlled: Any) -> dict[str, Any]:
    if not isinstance(controlled, dict) or set(controlled) != CONTROLLED_KEYS:
        raise ValueError("controlled profile fields do not match schema")
    for key in STRING_CONTROLLED_KEYS:
        value = controlled[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"controlled profile field {key} must be non-empty")
    for key in ("captureContractVersion", "comparatorSchemaVersion"):
        value = controlled[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"controlled profile field {key} must be positive")
    return controlled


def _validate_profile(
    payload: dict[str, Any], *, expected_profile: str, source_sha: str
) -> str:
    if payload.get("schemaVersion") != 2:
        raise ValueError("current profile schemaVersion must be 2")
    if payload.get("profile") != expected_profile:
        raise ValueError("current profile label does not match visual manifest")
    if payload.get("currentSHA") != source_sha:
        raise ValueError("current profile currentSHA does not match source SHA")

    controlled = _validate_controlled_profile(payload.get("controlled"))
    stored = payload.get("profileFingerprint")
    calculated = _canonical_fingerprint(controlled)
    if not isinstance(stored, str) or not SHA256_RE.fullmatch(stored):
        raise ValueError("current profile fingerprint is malformed")
    if stored != calculated:
        raise ValueError("current profile fingerprint does not match controlled profile")
    return stored


def _validate_case_id(case_id: Any) -> str:
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        raise ValueError(f"invalid visual case id: {case_id!r}")
    return case_id


def _reject_symlink_components(repo_root: Path, relative_path: Path) -> None:
    current = repo_root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"rolling visual capture path contains symlink: {relative_path}")


def _read_capture(repo_root: Path, relative: Any) -> bytes:
    if not isinstance(relative, str) or not relative:
        raise ValueError("rolling visual current path must be non-empty")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("rolling visual current path escapes capture root")

    expected_prefix = Path("artifacts/visual/current")
    try:
        relative_path.relative_to(expected_prefix)
    except ValueError as exc:
        raise ValueError("rolling visual current path must stay under capture root") from exc

    _reject_symlink_components(repo_root, relative_path)
    candidate = repo_root / relative_path
    if not candidate.is_file():
        raise ValueError(f"rolling visual capture is not a regular file: {relative}")
    return candidate.read_bytes()


def _validate_manifest(payload: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if payload.get("schemaVersion") != 1:
        raise ValueError("visual manifest schemaVersion must be 1")
    profile = payload.get("profile")
    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("visual manifest profile must be non-empty")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("visual manifest cases must be an array")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for raw in cases:
        if not isinstance(raw, dict):
            raise ValueError("visual manifest cases must be objects")
        case_id = _validate_case_id(raw.get("id"))
        if case_id in seen:
            raise ValueError(f"duplicate visual case id: {case_id}")
        seen.add(case_id)
        baseline = raw.get("baseline")
        if baseline not in {"git", "rolling-main"}:
            raise ValueError(f"unsupported baseline source for {case_id}")
        normalized.append(raw)
    return profile, normalized


def _validate_provenance(
    repository: str,
    workflow: str,
    run_id: str,
    run_attempt: int,
    source_sha: str,
) -> None:
    owner_repo = repository.split("/")
    if len(owner_repo) != 2 or not all(owner_repo):
        raise ValueError("repository must be owner/repo")
    if not workflow or "/" in workflow or not workflow.endswith((".yml", ".yaml")):
        raise ValueError("workflow must be a workflow file name")
    if not run_id.isdigit() or int(run_id) <= 0:
        raise ValueError("run id must be a positive integer string")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt <= 0:
        raise ValueError("run attempt must be positive")
    if not GIT_SHA_RE.fullmatch(source_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal characters")


def _write_bundle(
    *,
    staging_root: Path,
    profile_payload: dict[str, Any],
    rolling: list[tuple[str, bytes, str]],
    repository: str,
    workflow: str,
    run_id: str,
    run_attempt: int,
    source_sha: str,
    profile_fingerprint: str,
    previous_baseline_reference: str | None,
) -> None:
    images_root = staging_root / "images"
    images_root.mkdir(parents=True)
    (staging_root / "profile.json").write_text(
        json.dumps(profile_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for case_id, image_data, _digest in rolling:
        (images_root / f"{case_id}.png").write_bytes(image_data)

    bundle = {
        "schemaVersion": 1,
        "sourceRepository": repository,
        "workflow": workflow,
        "sourceRunID": run_id,
        "runAttempt": run_attempt,
        "sourceSHA": source_sha,
        "profileFingerprint": profile_fingerprint,
        "previousBaselineReference": previous_baseline_reference,
        "cases": [
            {"id": case_id, "digest": digest}
            for case_id, _image_data, digest in rolling
        ],
    }
    (staging_root / "bundle-manifest.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_bundle(
    *,
    repo_root: Path,
    manifest_path: Path,
    current_profile_path: Path,
    output_root: Path,
    repository: str,
    workflow: str,
    run_id: str,
    run_attempt: int,
    source_sha: str,
    previous_baseline_reference: str | None,
) -> None:
    repo_root = repo_root.resolve()
    manifest_path = manifest_path.resolve()
    current_profile_path = current_profile_path.resolve()
    output_root = output_root.resolve()

    if output_root.exists():
        raise ValueError("output directory already exists")
    _validate_provenance(repository, workflow, run_id, run_attempt, source_sha)

    manifest_payload = _load_json(manifest_path, "visual manifest")
    profile_label, cases = _validate_manifest(manifest_payload)
    profile_payload = _load_json(current_profile_path, "current profile")
    profile_fingerprint = _validate_profile(
        profile_payload, expected_profile=profile_label, source_sha=source_sha
    )

    rolling: list[tuple[str, bytes, str]] = []
    for test_case in cases:
        if test_case["baseline"] != "rolling-main":
            continue
        case_id = test_case["id"]
        image_data = _read_capture(repo_root, test_case.get("current"))
        rolling.append((case_id, image_data, _sha256_bytes(image_data)))
    rolling.sort(key=lambda item: item[0])

    if previous_baseline_reference == "":
        raise ValueError("previous baseline reference must be non-empty when provided")

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=".visual-baseline.", dir=output_root.parent)
    )
    try:
        _write_bundle(
            staging_root=staging_root,
            profile_payload=profile_payload,
            rolling=rolling,
            repository=repository,
            workflow=workflow,
            run_id=run_id,
            run_attempt=run_attempt,
            source_sha=source_sha,
            profile_fingerprint=profile_fingerprint,
            previous_baseline_reference=previous_baseline_reference,
        )
        staging_root.replace(output_root)
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--current-profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--previous-baseline-reference")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    profile_path = (
        args.current_profile
        if args.current_profile.is_absolute()
        else repo_root / args.current_profile
    )
    try:
        build_bundle(
            repo_root=repo_root,
            manifest_path=manifest_path,
            current_profile_path=profile_path,
            output_root=args.output,
            repository=args.repository,
            workflow=args.workflow,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            source_sha=args.source_sha,
            previous_baseline_reference=args.previous_baseline_reference,
        )
    except (OSError, ValueError) as exc:
        print(f"build-baseline-bundle: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
