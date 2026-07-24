# pi-hook.sh — auto re-apply pi-local-mods after the native `pi update`.
#
# Source this from your shell profile (~/.zshrc or ~/.bashrc). apply.sh installs
# it automatically via scripts/install_hook.py:
#
#     [ -f "$HOME/home/pi-local-mods/scripts/pi-hook.sh" ] && \
#         source "$HOME/home/pi-local-mods/scripts/pi-hook.sh"
#
# After every successful `pi update`, this re-applies the patches to the updated
# Pi and verifies them (scripts/post_update.py). On any failure it prints a
# clean, copyable error report to stderr.
#
# Why a shell hook instead of patching Pi's own update routine? Because
# `pi update` reinstalls Pi and would wipe any in-Pi hook (chicken-and-egg).
# This wrapper lives in your shell profile, so it survives updates and fires
# every time `pi update` exits successfully. It overrides `pi` as a function
# and calls the real binary via `command pi`, only acting on a successful
# `update` and preserving its exit code.
#
# Override the mods directory with PI_LOCAL_MODS_DIR if you clone elsewhere.
pi() {
    command pi "$@"
    local __pi_code=$?
    if [[ "$1" == "update" && "$__pi_code" -eq 0 ]]; then
        local __mods_dir="${PI_LOCAL_MODS_DIR:-$HOME/home/pi-local-mods}"
        if [[ -f "$__mods_dir/scripts/post_update.py" ]]; then
            ( cd "$__mods_dir" && python3 scripts/post_update.py ) >&2 || true
        fi
    fi
    return "$__pi_code"
}
