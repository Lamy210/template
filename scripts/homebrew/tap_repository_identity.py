from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.common.bounded_json import (  # noqa: E402
    BoundedJsonError,
    load_bounded_json_file,
)
from scripts.common.repository_name import is_canonical_repository_name  # noqa: E402


def validate_tap_repository_identity(
    document: object,
    *,
    expected_repository: str,
    expected_default_branch: str,
    expected_repository_id: int | None = None,
) -> tuple[list[str], dict[str, object] | None]:
    errors: list[str] = []

    if not is_canonical_repository_name(expected_repository):
        errors.append("expected repository must be canonical owner/repo")

    if (
        not isinstance(expected_default_branch, str)
        or not expected_default_branch
        or "\n" in expected_default_branch
        or "\r" in expected_default_branch
    ):
        errors.append("expected default branch must be a non-empty single line")

    if expected_repository_id is not None and (
        type(expected_repository_id) is not int or expected_repository_id <= 0
    ):
        errors.append("expected repository id must be a positive integer")

    if not isinstance(document, dict):
        errors.append("tap repository response must be a JSON object")
        return errors, None

    repository_id = document.get("id")
    full_name = document.get("full_name")
    default_branch = document.get("default_branch")
    clone_url = document.get("clone_url")
    ssh_url = document.get("ssh_url")

    if type(repository_id) is not int or repository_id <= 0:
        errors.append("tap repository id must be a positive integer")
    elif (
        expected_repository_id is not None
        and repository_id != expected_repository_id
    ):
        errors.append(
            "tap repository id does not match the trusted repository snapshot"
        )

    if not is_canonical_repository_name(full_name):
        errors.append("tap repository full_name must be canonical owner/repo")
    elif (
        is_canonical_repository_name(expected_repository)
        and full_name.casefold() != expected_repository.casefold()
    ):
        errors.append("tap repository full_name does not match expected repository")

    if default_branch != expected_default_branch:
        errors.append("tap repository default_branch does not match expected branch")

    for field, value in (("clone_url", clone_url), ("ssh_url", ssh_url)):
        if (
            not isinstance(value, str)
            or not value
            or "\n" in value
            or "\r" in value
        ):
            errors.append(f"tap repository {field} must be a non-empty single line")

    if is_canonical_repository_name(full_name):
        canonical_clone_url = f"https://github.com/{full_name}.git"
        canonical_ssh_url = f"git@github.com:{full_name}.git"
        if clone_url != canonical_clone_url:
            errors.append(
                "tap repository clone_url does not match canonical full_name"
            )
        if ssh_url != canonical_ssh_url:
            errors.append(
                "tap repository ssh_url does not match canonical full_name"
            )

    if errors:
        return errors, None

    assert isinstance(repository_id, int)
    assert isinstance(full_name, str)
    assert isinstance(default_branch, str)
    assert isinstance(clone_url, str)
    assert isinstance(ssh_url, str)
    return (
        [],
        {
            "repositoryId": repository_id,
            "fullName": full_name,
            "defaultBranch": default_branch,
            "cloneUrl": clone_url,
            "sshUrl": ssh_url,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate canonical Homebrew tap repository identity from the "
            "GitHub REST repository response."
        )
    )
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--repository-id", type=int)
    args = parser.parse_args(argv)

    try:
        document = load_bounded_json_file(
            args.metadata,
            label="tap repository metadata",
        )
    except BoundedJsonError as error:
        print(error, file=sys.stderr)
        return 1

    errors, identity = validate_tap_repository_identity(
        document,
        expected_repository=args.repository,
        expected_default_branch=args.default_branch,
        expected_repository_id=args.repository_id,
    )
    for error in errors:
        print(error, file=sys.stderr)
    if errors or identity is None:
        return 1

    print(identity["repositoryId"])
    print(identity["fullName"])
    print(identity["defaultBranch"])
    print(identity["cloneUrl"])
    print(identity["sshUrl"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
