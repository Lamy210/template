#!/usr/bin/env bash

is_canonical_repository_name() {
  (($# == 1)) || return 1

  local repository="$1"
  local owner
  local name

  [[ "${repository}" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || return 1

  owner="${repository%%/*}"
  name="${repository#*/}"
  [[ "${owner}" != "." && "${owner}" != ".." && "${name}" != "." && "${name}" != ".." ]]
}
