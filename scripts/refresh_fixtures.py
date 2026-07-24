#!/usr/bin/env python3
"""Refresh the frozen test fixtures from the currently installed Pi.

Captures the *clean* (unpatched) source of every patched file and copies it into
tests/fixtures/, then writes tests/fixtures/VERSION with the installed Pi
version. Run this after a Pi upgrade once patches are confirmed working, then
commit the refreshed snapshots.

The clean source is taken from the live file when it is already unpatched, else
from the `.pi-local-mods.bak` captured on first apply. If neither is clean the
script aborts (reinstall Pi clean first).
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("pi_local_mods_apply", ROOT / "scripts" / "apply.py")
apply = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(apply)

FIXTURES = ROOT / "tests" / "fixtures"

# (apply-module path attribute, fixture destination relative to tests/fixtures)
TARGETS = [
    ("INTERACTIVE", "pi/dist/modes/interactive/interactive-mode.js"),
    ("FOOTER", "pi/dist/modes/interactive/components/footer.js"),
    ("CUSTOM_EDITOR", "pi/dist/modes/interactive/components/custom-editor.js"),
    ("CLIPBOARD_IMAGE", "pi/dist/utils/clipboard-image.js"),
    ("TERMINAL", "pi/node_modules/@earendil-works/pi-tui/dist/terminal.js"),
]


def main() -> int:
    version = apply.installed_pi_version()
    if not version:
        raise SystemExit("Could not determine installed Pi version (package.json missing).")

    for attr, rel in TARGETS:
        live = getattr(apply, attr)
        marker = apply.CLEAN_MARKERS[attr]
        src = apply.clean_source(live, marker)
        dest = FIXTURES / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if marker in dest.read_text():
            raise SystemExit(f"{dest} still contains patch marker {marker!r}; source was not clean.")
        print(f"refreshed {rel}  (from {src.name})")

    (FIXTURES / "VERSION").write_text(version + "\n")
    print(f"pinned fixtures to Pi {version}")

    print("running patch test suite...")
    subprocess.run([sys.executable, "-m", "unittest", "scripts.test_apply"], cwd=str(ROOT), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
