# --> auto-attach to tmux on interactive shells (set NO_TMUX=1 to skip)
# Reattach to the most recently attached workspace. SSH shells get their own
# grouped session (shared windows, independent active-window). Create `main`
# only when no workspace exists yet.
if [[ -o interactive ]] && [[ -z "$TMUX" ]] && [[ -z "$NO_TMUX" ]] \
   && command -v tmux >/dev/null 2>&1 \
   && [[ "$TERM" != screen* ]] && [[ "$TERM" != tmux* ]]; then
  target_session=$(
    tmux list-sessions -F '#{?session_last_attached,#{session_last_attached},0} #{session_id}' 2>/dev/null \
      | sort -nr \
      | awk 'NR == 1 { print $2; exit }'
  )

  if [[ -z "$target_session" ]]; then
    tmux new-session -d -s main
    target_session=$(tmux display-message -p -t main '#{session_id}')
  fi

  if [[ -n "$SSH_CONNECTION" ]] || [[ -n "$SSH_TTY" ]]; then
    exec tmux new-session -t "$target_session" -s "ssh-$$"
  else
    exec tmux attach-session -t "$target_session"
  fi
fi
