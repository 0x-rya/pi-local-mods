#!/usr/bin/env bash
# Live `git status -sb` for REPO. Repaints every $POLL seconds (default 2).
set -u
REPO="${1:-$PWD}"
NAME=$(basename "$REPO")
INTERVAL="${POLL:-2}"

while true; do
  if out=$(git -C "$REPO" -c color.ui=always -c color.status=always status -sb 2>&1); then
    :
  else
    out="(git status failed: $out)"
  fi
  printf '\033[H\033[J\033[1;36m── status · %s ──\033[0m\n\n%s\n' "$NAME" "$out"
  sleep "$INTERVAL"
done
