from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.validate_rulesets import validate_main_solo


EXPECTED_NAME = "Solo default branch"
RUNTIME_FIELDS = {
    "id",
    "node_id",
    "source",
    "source_type",
    "_links",
    "created_at",
    "updated_at",
    "current_user_can_bypass",
}


def validate_live_main_ruleset(
    document: object,
    *,
    expected_repository: str,
) -> list[str]:
    if not isinstance(document, dict):
        return ["live main Ruleset must be a JSON object"]

    errors: list[str] = []

    if document.get("name") != EXPECTED_NAME:
        errors.append(f"name must equal {EXPECTED_NAME!r}")
    if document.get("source_type") != "Repository":
        errors.append("source_type must equal 'Repository'")
    if document.get("source") != expected_repository:
        errors.append("source must equal expected repository")

    ruleset_id = document.get("id")
    if type(ruleset_id) is not int or ruleset_id <= 0:
        errors.append("id must be a positive integer")

    if "bypass_actors" in document and document.get("bypass_actors") != []:
        errors.append("bypass_actors must be empty when returned by GitHub")

    if (
        "current_user_can_bypass" in document
        and document.get("current_user_can_bypass") != "never"
    ):
        errors.append("current_user_can_bypass must equal 'never' when returned by GitHub")

    canonical = {
        key: value
        for key, value in document.items()
        if key not in RUNTIME_FIELDS
    }
    canonical.setdefault("bypass_actors", [])

    errors.extend(validate_main_solo(canonical))
    return errors


def _load_json(path: str) -> object:
    if path == "-":
        try:
            return json.load(sys.stdin)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"invalid JSON from stdin: {error.msg} at line {error.lineno} column {error.colno}"
            ) from error

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as error:
        raise SystemExit(f"failed to read {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"{path}: invalid JSON: {error.msg} at line {error.lineno} column {error.colno}"
        ) from error


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(
            "Usage: audit_main_ruleset.py <ruleset-json|-> owner/repo",
            file=sys.stderr,
        )
        return 2

    path, repository = args
    if (
        "/" not in repository
        or repository.startswith("/")
        or repository.endswith("/")
        or repository.count("/") != 1
    ):
        print("repository must be in owner/repo form", file=sys.stderr)
        return 2

    document = _load_json(path)
    errors = validate_live_main_ruleset(
        document,
        expected_repository=repository,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print(
        f"Live Ruleset {EXPECTED_NAME!r} matches the Solo default-branch contract "
        f"for {repository}."
    )
    if isinstance(document, dict) and "bypass_actors" not in document:
        print(
            "Note: GitHub omitted bypass_actors for this read-only caller; "
            "verify bypass actors during administrator import/review.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
