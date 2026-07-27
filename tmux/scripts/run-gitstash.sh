#!/usr/bin/env bash
# Live `git stash list` for REPO. Repaints every $POLL seconds (default 2).
set -u
REPO="${1:-$PWD}"
NAME=$(basename "$REPO")
INTERVAL="${POLL:-2}"

while true; do
  out=$(git -C "$REPO" -c color.ui=always stash list 2>&1)
  if [ -z "$out" ]; then
    out=$'\033[2m(no stashes)\033[0m'
  fi
  printf '\033[H\033[J\033[1;36m── stash · %s ──\033[0m\n\n%s\n' "$NAME" "$out"
  sleep "$INTERVAL"
done
