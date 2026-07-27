#!/usr/bin/env bash
# Add another git repo's log below the existing right-column logs (or below
# the terminal if none yet). Opens the panel if currently closed.
set -euo pipefail

INPUT="${1:-}"
if [ -z "$INPUT" ]; then
  printf 'Repository path: '
  IFS= read -r INPUT || exit 0
  [ -n "$INPUT" ] || exit 0
fi

INPUT="${INPUT/#\~/$HOME}"
if ! REPO=$(cd "$INPUT" 2>/dev/null && pwd); then
  tmux display-message "add-repo: path not found: $INPUT"
  exit 1
fi
if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  tmux display-message "add-repo: not a git repo: $REPO"
  exit 1
fi
case "$REPO" in
  *';'*|*$'\n'*|*$'\r'*)
    tmux display-message "add-repo: paths containing semicolons or newlines are unsupported"
    exit 1
    ;;
esac

WIN_ID=$(tmux display -p '#{window_id}')
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

REPOS=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_repos 2>/dev/null || true)
if [ -n "${REPOS:-}" ]; then
  ALREADY_ADDED=0
  IFS=';' read -ra EXISTING_REPOS <<< "$REPOS"
  for existing in "${EXISTING_REPOS[@]}"; do
    if [ "$existing" = "$REPO" ]; then
      ALREADY_ADDED=1
      break
    fi
  done
  if [ "$ALREADY_ADDED" = "0" ]; then
    REPOS="$REPOS;$REPO"
  fi
else
  REPOS="bonsai;$REPO"
fi
tmux set-window-option -t "$WIN_ID" @side_panel_repos "$REPOS"

STATE=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_state 2>/dev/null || echo closed)
if [ "$STATE" != "open" ]; then
  exec "$SCRIPTS/toggle-side-panel.sh"
fi

# panel is open: split below the last gitlog pane, or below the terminal if no gitlogs yet
LAST_GITLOG=$(tmux list-panes -t "$WIN_ID" -F '#{pane_id}|#{@panel_role}' \
              | awk -F'|' '$2=="gitlog"{print $1}' | tail -1)
TERMINAL=$(tmux list-panes -t "$WIN_ID" -F '#{pane_id}|#{@in_side_panel}' \
           | awk -F'|' '$2!="1"{print $1; exit}')
TARGET="${LAST_GITLOG:-$TERMINAL}"

if [ -z "$TARGET" ]; then
  tmux set-window-option -t "$WIN_ID" @side_panel_state closed
  exec "$SCRIPTS/toggle-side-panel.sh"
fi

ORIG_PANE=$(tmux display -p '#{pane_id}')
printf -v GITLOG_COMMAND '%q %q' "$SCRIPTS/run-gitlog.sh" "$REPO"
NEW=$(tmux split-window -v -P -F '#{pane_id}' -t "$TARGET" -c "$REPO" "$GITLOG_COMMAND")
tmux set-option -p -t "$NEW" @in_side_panel 1
tmux set-option -p -t "$NEW" @panel_role gitlog
tmux set-option -p -t "$NEW" remain-on-exit on
tmux select-pane -t "$ORIG_PANE"
