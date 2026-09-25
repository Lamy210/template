#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.homebrew.tap_remote import validate_tap_remote_urls


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind effective tap Git fetch/push remotes to canonical GitHub repository URLs."
    )
    parser.add_argument("--fetch-url", required=True)
    parser.add_argument("--push-url", required=True)
    parser.add_argument("--canonical-https-url", required=True)
    parser.add_argument("--canonical-ssh-url", required=True)
    args = parser.parse_args()

    errors = validate_tap_remote_urls(
        fetch_url=args.fetch_url,
        push_url=args.push_url,
        canonical_https_url=args.canonical_https_url,
        canonical_ssh_url=args.canonical_ssh_url,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
