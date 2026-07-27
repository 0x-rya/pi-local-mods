#!/usr/bin/env bash
# Status-line indicator: shows "panel: N repo(s)" when open, "panel: off" otherwise.
WIN_ID="${1:-}"
[ -z "$WIN_ID" ] && exit 0

STATE=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_state 2>/dev/null || echo closed)
REPOS=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_repos 2>/dev/null || true)

if [ "$STATE" = "open" ]; then
  if [ -n "${REPOS:-}" ]; then
    n=$(awk -F';' '{c=0; for (i=1;i<=NF;i++) if ($i!="" && $i!="bonsai") c++; print c}' <<< "$REPOS")
    printf 'panel: on (%d repo%s)' "$n" "$([ "$n" = "1" ] && echo "" || echo s)"
  else
    printf 'panel: on'
  fi
else
  printf 'panel: off'
fi
