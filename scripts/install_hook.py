#!/usr/bin/env python3
"""Idempotently install the `pi update` auto re-apply hook into a shell rc file.

Adds a `source <repo>/scripts/pi-hook.sh` block to the rc file (default
~/.zshrc) the first time, backing it up to `<rc>.pi-local-mods.bak`. Skips
silently on subsequent runs. Designed to be called by apply.sh every time so
the hook is always present after updates wipe Pi's own files.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

MARKER = "pi-hook.sh"


def install(rc_path: Path | str, hook_path: Path | str, marker: str = MARKER) -> str:
    """Ensure the hook is sourced from `rc_path`. Returns 'installed' or 'present'."""
    rc_path = Path(rc_path).expanduser()
    hook_path = str(Path(hook_path))
    begin = "# >>> pi-local-mods: re-apply local Pi patches after 'pi update' >>>"
    end = "# <<< pi-local-mods <<<"
    hook_line = f'[ -f "{hook_path}" ] && source "{hook_path}"'

    rc_path.parent.mkdir(parents=True, exist_ok=True)
    if not rc_path.exists():
        rc_path.touch()

    content = rc_path.read_text()
    if marker in content or hook_line in content:
        return "present"

    bak = rc_path.with_name(rc_path.name + ".pi-local-mods.bak")
    if not bak.exists():
        shutil.copy2(rc_path, bak)

    body = content
    if body and not body.endswith("\n"):
        body += "\n"
    if body:
        body += "\n"  # blank separator line before the block
    body += f"{begin}\n{hook_line}\n{end}\n"
    rc_path.write_text(body)
    return "installed"


def main() -> int:
    rc = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".zshrc"
    hook = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / "pi-hook.sh"
    result = install(rc, hook)
    if result == "present":
        print(f"pi-local-mods hook already present in {rc}")
    else:
        print(f"Installed pi-local-mods hook into {rc} (backup: {rc.name}.pi-local-mods.bak)")
        print("Start a new shell (or: source ~/" + rc.name + ") to enable 'pi update' auto re-apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
