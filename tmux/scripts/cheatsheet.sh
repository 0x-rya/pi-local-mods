#!/usr/bin/env bash
# Show the tmux cheatsheet in a popup. Press q or Esc to close.
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
exec tmux display-popup -E -w 82% -h 92% \
  "less -R --tabs=4 '$SCRIPTS/cheatsheet.txt'"
