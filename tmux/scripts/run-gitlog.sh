#!/usr/bin/env bash
# Live `git log --graph --all` for REPO. Repaints every $POLL seconds.
# Scroll back via tmux copy mode: prefix [ , then arrow keys / PageUp.
set -u
REPO="${1:-$PWD}"
NAME=$(basename "$REPO")
INTERVAL="${POLL:-3}"
PRETTY='%C(auto)%h%C(reset) %C(dim white)%ad%C(reset) %C(auto)%d%C(reset) %s %C(green)(%cr)%C(reset) %C(blue)<%an>%C(reset)%n'

while true; do
  rows=$(tput lines 2>/dev/null || echo 30)
  show=$((rows - 4))
  [ "$show" -lt 1 ] && show=1
  out=$(git -C "$REPO" log --graph --all --color=always --decorate \
        --abbrev-commit --date=short --pretty=format:"$PRETTY" 2>&1 \
        | head -n "$show")
  printf '\033[H\033[J\033[1;36m── %s ──\033[0m\n\n%s\n' "$NAME" "$out"
  sleep "$INTERVAL"
done
