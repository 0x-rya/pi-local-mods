# pi-hook.sh — auto re-apply pi-local-mods after the native `pi update`.
#
# Source this from your shell profile (~/.zshrc or ~/.bashrc):
#
#     [ -f "$HOME/home/pi-local-mods/scripts/pi-hook.sh" ] && \
#         source "$HOME/home/pi-local-mods/scripts/pi-hook.sh"
#
# Then every successful `pi update` will automatically re-apply the patches to
# the freshly updated Pi and run the drift smoke test + patch suite. If a patch
# drifted on the new Pi, apply.py aborts and the hook reports it.
#
# Why a shell hook instead of patching Pi's own update routine? Because
# `pi update` reinstalls Pi and would wipe any in-Pi hook (chicken-and-egg).
# This wrapper lives in your shell profile, so it is untouched by updates and
# fires every time `pi update` exits successfully.
#
# Override the mods directory with PI_LOCAL_MODS_DIR if you clone elsewhere.
pi() {
    command pi "$@"
    local __pi_code=$?
    if [[ "$1" == "update" && "$__pi_code" -eq 0 ]]; then
        local __mods_dir="${PI_LOCAL_MODS_DIR:-$HOME/home/pi-local-mods}"
        if [[ -f "$__mods_dir/scripts/apply.py" ]]; then
            echo "==> pi-local-mods: re-applying patches to updated Pi" >&2
            if ( cd "$__mods_dir" && python3 scripts/apply.py ) >&2; then
                python3 "$__mods_dir/scripts/smoke.py" >&2 \
                    || echo "!! pi-local-mods: smoke reported drift" >&2
                ( cd "$__mods_dir" && python3 -m unittest scripts.test_apply ) >&2 \
                    || echo "!! pi-local-mods: patch tests failed" >&2
                echo "==> pi-local-mods: done. Restart Pi to use the patched runtime." >&2
            else
                echo "!! pi-local-mods: apply failed — patches need updating for the new Pi." >&2
                echo "!!   Fix scripts/apply.py, then run: python3 scripts/refresh_fixtures.py" >&2
            fi
        fi
    fi
    return "$__pi_code"
}
