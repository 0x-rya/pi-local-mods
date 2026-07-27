#!/usr/bin/env bash
# Toggle layout:
#   ┌────────────┬───────────────────────┐
#   │ git status │  terminal             │
#   │            │                       │
#   ├────────────┤                       │
#   │ git stash  │                       │
#   │            ├───────────────────────┤
#   ├────────────┤  git log (cwd repo)   │
#   │ bonsai     │  …                    │
#   └────────────┴───────────────────────┘
# Bonsai is stashed (break-pane to a hidden window) on close so the same tree
# is restored on next open. Status / stash / git log panes auto-refresh (~2-3s).
set -euo pipefail

WIN_ID=$(tmux display -p '#{window_id}')
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
STASH_WIN="_bonsai_${WIN_ID//@/}"

STATE=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_state 2>/dev/null || echo closed)

panel_panes() {
  tmux list-panes -t "$WIN_ID" -F '#{pane_id}|#{@in_side_panel}|#{@is_bonsai}' \
    | awk -F'|' '$2=="1"{print $1":"$3}'
}
find_stashed_bonsai() {
  tmux list-panes -a -F '#{pane_id}|#{@is_bonsai}|#{@in_side_panel}' 2>/dev/null \
    | awk -F'|' '$2=="1" && $3!="1"{print $1; exit}'
}
mark() {  # mark $pane $role
  tmux set-option -p -t "$1" @in_side_panel 1
  tmux set-option -p -t "$1" @panel_role "$2"
  tmux set-option -p -t "$1" remain-on-exit on
}

if [ "$STATE" = "open" ]; then
  for entry in $(panel_panes); do
    p="${entry%:*}"
    is_b="${entry#*:}"
    if [ "$is_b" = "1" ]; then
      tmux set-option -p -u -t "$p" @in_side_panel 2>/dev/null || true
      tmux set-option -p -u -t "$p" @panel_role 2>/dev/null || true
      if ! tmux break-pane -d -s "$p" -n "$STASH_WIN" 2>/dev/null; then
        tmux kill-pane -t "$p" 2>/dev/null || true
      fi
    else
      tmux kill-pane -t "$p" 2>/dev/null || true
    fi
  done
  tmux set-window-option -t "$WIN_ID" @side_panel_state closed
  exit 0
fi

# --- open ---
CWD=$(tmux display -p '#{pane_current_path}')

REPOS=$(tmux show-window-options -v -t "$WIN_ID" @side_panel_repos 2>/dev/null || true)
if [ -z "${REPOS:-}" ]; then
  if git -C "$CWD" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    case "$CWD" in
      *';'*|*$'\n'*|*$'\r'*)
        tmux display-message "side panel: repository paths containing semicolons or newlines are unsupported"
        exit 1
        ;;
    esac
    REPOS="bonsai;$CWD"
  else
    REPOS="bonsai"
  fi
  tmux set-window-option -t "$WIN_ID" @side_panel_repos "$REPOS"
fi

ORIG_PANE=$(tmux display -p '#{pane_id}')

IFS=';' read -ra ITEMS <<< "$REPOS"
PRIMARY_REPO=""
HAS_BONSAI=0
for item in "${ITEMS[@]}"; do
  [ -z "$item" ] && continue
  if [ "$item" = "bonsai" ]; then
    HAS_BONSAI=1
  elif [ -z "$PRIMARY_REPO" ]; then
    PRIMARY_REPO="$item"
  fi
done

# --- left column: bonsai + (optional) status + stash ---
BONSAI_PANE=""
if [ "$HAS_BONSAI" = "1" ]; then
  STASH_BONSAI=$(find_stashed_bonsai)
  if [ -n "$STASH_BONSAI" ]; then
    tmux join-pane -h -b -l 20% -s "$STASH_BONSAI" -t "$ORIG_PANE"
    BONSAI_PANE="$STASH_BONSAI"
  else
    BONSAI_PANE=$(tmux split-window -h -b -l 20% -P -F '#{pane_id}' \
                    -t "$ORIG_PANE" -c "$HOME" "$SCRIPTS/run-bonsai.sh")
    tmux set-option -p -t "$BONSAI_PANE" @is_bonsai 1
  fi
  mark "$BONSAI_PANE" bonsai
fi

if [ -n "$BONSAI_PANE" ] && [ -n "$PRIMARY_REPO" ]; then
  # status pane goes ABOVE bonsai at 60% — leaves bonsai 40% bottom (matches gitlog).
  printf -v STATUS_COMMAND '%q %q' "$SCRIPTS/run-gitstatus.sh" "$PRIMARY_REPO"
  STATUS_PANE=$(tmux split-window -v -b -l 60% -P -F '#{pane_id}' \
                  -t "$BONSAI_PANE" -c "$PRIMARY_REPO" "$STATUS_COMMAND")
  mark "$STATUS_PANE" gitstatus
  # stash takes the bottom 35% of the status region; status keeps 65%.
  printf -v STASH_COMMAND '%q %q' "$SCRIPTS/run-gitstash.sh" "$PRIMARY_REPO"
  STASH_PANE=$(tmux split-window -v -l 35% -P -F '#{pane_id}' \
                 -t "$STATUS_PANE" -c "$PRIMARY_REPO" "$STASH_COMMAND")
  mark "$STASH_PANE" gitstash
fi

# --- right column: git logs stacked below ORIG ---
GITLOG_PREV="$ORIG_PANE"
for item in "${ITEMS[@]}"; do
  [ -z "$item" ] && continue
  [ "$item" = "bonsai" ] && continue
  printf -v GITLOG_COMMAND '%q %q' "$SCRIPTS/run-gitlog.sh" "$item"
  NEW=$(tmux split-window -v -l 40% -P -F '#{pane_id}' \
          -t "$GITLOG_PREV" -c "$item" "$GITLOG_COMMAND")
  mark "$NEW" gitlog
  GITLOG_PREV="$NEW"
done

tmux set-window-option -t "$WIN_ID" @side_panel_state open
tmux select-pane -t "$ORIG_PANE"
