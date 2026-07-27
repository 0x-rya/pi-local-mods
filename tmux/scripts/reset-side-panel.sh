#!/usr/bin/env bash
# Clear the panel's repo list and close it. Also kills any stashed bonsai so
# the next open starts a fresh tree.
set -euo pipefail

WIN_ID=$(tmux display -p '#{window_id}')

STATE=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_state 2>/dev/null || echo closed)
if [ "$STATE" = "open" ]; then
  for p in $(tmux list-panes -t "$WIN_ID" -F '#{pane_id}|#{@in_side_panel}' \
             | awk -F'|' '$2=="1"{print $1}'); do
    tmux kill-pane -t "$p" 2>/dev/null || true
  done
fi

# kill any stashed bonsai (panes marked @is_bonsai that are not in any side panel)
for p in $(tmux list-panes -a -F '#{pane_id}|#{@is_bonsai}|#{@in_side_panel}' 2>/dev/null \
           | awk -F'|' '$2=="1" && $3!="1"{print $1}'); do
  tmux kill-pane -t "$p" 2>/dev/null || true
done

tmux set-window-option -t "$WIN_ID" -u @side_panel_repos 2>/dev/null || true
tmux set-window-option -t "$WIN_ID" @side_panel_state closed
tmux display-message "side panel reset"
