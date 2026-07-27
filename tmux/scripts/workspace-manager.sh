#!/usr/bin/env bash
# Safe workspace (tmux session) creation, window moves, and deletion.
# Invoked in a tmux popup by the n, m, and Q prefix bindings.

set -u

ACTION=${1:-}
CLIENT=${2:-}
ARG3=${3:-}
ARG4=${4:-}

pause_if_interactive() {
  if [ -t 0 ]; then
    printf '\nPress Enter to close...'
    IFS= read -r _ || true
  fi
}

fail() {
  printf '\nError: %s\n' "$1" >&2
  pause_if_interactive
  exit 1
}

session_exists() {
  tmux has-session -t "$1" 2>/dev/null
}

session_name_for_id() {
  tmux display-message -p -t "$1" '#{session_name}' 2>/dev/null
}

sanitize_for_display() {
  LC_ALL=C printf '%s' "$1" | tr '\000-\037\177' '?'
}

session_name_exists() {
  local wanted=$1 id existing
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    existing=$(session_name_for_id "$id") || continue
    [ "$existing" = "$wanted" ] && return 0
  done < <(tmux list-sessions -F '#{session_id}' 2>/dev/null)
  return 1
}

choose_workspace() {
  local title=$1 exclude_id=${2:-} current_id=${3:-}
  local id name marker answer index i
  local -a ids=() names=()

  while IFS= read -r id; do
    [ -n "$id" ] || continue
    [ -n "$exclude_id" ] && [ "$id" = "$exclude_id" ] && continue
    name=$(session_name_for_id "$id") || continue
    name=$(sanitize_for_display "$name")
    ids[${#ids[@]}]=$id
    names[${#names[@]}]=$name
  done < <(tmux list-sessions -F '#{session_id}' 2>/dev/null)

  [ ${#ids[@]} -gt 0 ] || fail "No other workspace is available. Create one with prefix n first."

  printf '%s\n\n' "$title"
  i=0
  while [ $i -lt ${#ids[@]} ]; do
    marker=''
    [ -n "$current_id" ] && [ "${ids[$i]}" = "$current_id" ] && marker=' (current)'
    printf '  %d) %s%s\n' "$((i + 1))" "${names[$i]}" "$marker"
    i=$((i + 1))
  done

  while true; do
    printf '\nSelect 1-%d (or q to cancel): ' "${#ids[@]}"
    IFS= read -r answer || exit 0
    case "$answer" in
      ''|q|Q) exit 0 ;;
      *[!0-9]*) printf 'Please enter a listed number.\n' ;;
      *)
        if [ ${#answer} -gt 9 ]; then
          printf 'Please enter a listed number.\n'
          continue
        fi
        index=$((10#$answer - 1))
        if [ $index -ge 0 ] && [ $index -lt ${#ids[@]} ]; then
          SELECTED_SESSION_ID=${ids[$index]}
          SELECTED_SESSION_NAME=${names[$index]}
          return 0
        fi
        printf 'Please enter a listed number.\n'
        ;;
    esac
  done
}

window_index_in_session() {
  local session_id=$1 wanted_window_id=$2 window_id window_index
  while read -r window_id window_index; do
    if [ "$window_id" = "$wanted_window_id" ]; then
      printf '%s\n' "$window_index"
      return 0
    fi
  done < <(tmux list-windows -t "$session_id" -F '#{window_id} #{window_index}' 2>/dev/null)
  return 1
}

create_workspace() {
  local client=$1 pane_id=$2 name path new_session output

  [ -n "$client" ] || fail 'The invoking tmux client could not be identified.'
  [ -n "$pane_id" ] || fail 'The current tmux pane could not be identified.'

  printf 'New workspace name (letters, numbers, _ and -): '
  IFS= read -r name || exit 0
  [ -n "$name" ] || exit 0

  case "$name" in
    *[!A-Za-z0-9_-]*|[!A-Za-z0-9]*)
      fail 'Names must start with a letter or number and contain only letters, numbers, _ or -.'
      ;;
  esac

  session_name_exists "$name" && fail "A workspace named '$name' already exists."
  path=$(tmux display-message -p -t "$pane_id" '#{pane_current_path}' 2>/dev/null) || \
    fail 'The source pane no longer exists.'

  output=$(tmux new-session -d -P -F '#{session_id}' -s "$name" -c "$path" 2>&1) || \
    fail "Could not create workspace '$name': $output"
  new_session=$output

  if ! output=$(tmux switch-client -c "$client" -t "$new_session" 2>&1); then
    fail "Workspace '$name' was created, but tmux could not switch to it: $output"
  fi
}

send_window() {
  local client=$1 source_session=$2 source_window=$3 source_index count target command_output

  [ -n "$client" ] || fail 'The invoking tmux client could not be identified.'
  session_exists "$source_session" || fail 'The source workspace no longer exists.'
  source_index=$(window_index_in_session "$source_session" "$source_window") || \
    fail 'The source window no longer belongs to this workspace.'

  count=$(tmux display-message -p -t "$source_session" '#{session_windows}' 2>/dev/null) || \
    fail 'The source workspace no longer exists.'
  [ "$count" -gt 1 ] || fail 'Cannot send the only window; create another window first.'

  choose_workspace 'Send current window to:' "$source_session" "$source_session"
  target=$SELECTED_SESSION_ID
  session_exists "$target" || fail 'The selected workspace no longer exists.'

  # Resolve the source index again after the interactive selection. In one
  # tmux command queue, verify that index still contains the captured immutable
  # window ID and that the source has a spare window; then move by window ID.
  source_index=$(window_index_in_session "$source_session" "$source_window") || \
    fail 'The source window changed while the picker was open.'

  if ! command_output=$(tmux if-shell -F -t "${source_session}:${source_index}" \
      "#{&&:#{==:#{window_id},${source_window}},#{>:#{session_windows},1}}" \
      "move-window -s ${source_window} -t ${target}: ; move-window -r -t ${source_session}: ; move-window -r -t ${target}:" \
      "display-message -c ${client} 'Window or workspace changed; nothing was moved'" 2>&1); then
    fail "Could not send the window: $command_output"
  fi
}

delete_workspace() {
  local current_session=$1 target current_name answer output

  choose_workspace 'Delete workspace:' '' "$current_session"
  target=$SELECTED_SESSION_ID
  session_exists "$target" || fail 'The selected workspace no longer exists.'
  current_name=$(session_name_for_id "$target") || fail 'The selected workspace no longer exists.'
  current_name=$(sanitize_for_display "$current_name")

  printf "\nDelete workspace '%s' and all of its windows? [y/N] " "$current_name"
  IFS= read -r answer || exit 0
  case "$answer" in
    y|Y|yes|YES)
      if ! output=$(tmux kill-session -t "$target" 2>&1); then
        fail "Could not delete workspace '$current_name': $output"
      fi
      ;;
    *) exit 0 ;;
  esac
}

case "$ACTION" in
  new)    create_workspace "$CLIENT" "$ARG3" ;;
  send)   send_window "$CLIENT" "$ARG3" "$ARG4" ;;
  delete) delete_workspace "$ARG3" ;;
  *)      fail 'Unknown workspace action.' ;;
esac
