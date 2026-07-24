#!/usr/bin/env python3
"""Non-mutating drift smoke test.

For each patched file, takes the *clean* (unpatched) source from the installed
Pi, applies the patch to a throwaway temp copy, and `node --check`s the result.
This answers "do the patches still fit the currently installed Pi?" without
touching the live install.

Exits non-zero on any patch failure or syntax error, listing what drifted.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("pi_local_mods_apply", ROOT / "scripts" / "apply.py")
apply = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(apply)

# (path attribute, patch function, clean marker)
TARGETS = [
    ("INTERACTIVE", "patch_interactive", "class FixedBottomScrollLayout"),
    ("FOOTER", "patch_footer_component", "renderMainStatusLine"),
    ("CUSTOM_EDITOR", "patch_custom_editor", "setTopBorderProvider"),
    ("CLIPBOARD_IMAGE", "patch_clipboard_image", "readClipboardImageViaMacOsFileUrl"),
    ("TERMINAL", "patch_terminal", "Enable button-event mouse tracking"),
]


def main() -> int:
    version = apply.installed_pi_version() or "unknown"
    tmp = Path(tempfile.mkdtemp(prefix="pi-smoke-"))
    failures: list[str] = []

    for attr, fn_name, marker in TARGETS:
        live = getattr(apply, attr)
        try:
            src = apply.clean_source(live, marker)
        except SystemExit as e:
            failures.append(f"{fn_name}: {e}")
            continue

        dest = tmp / live.name
        shutil.copy2(src, dest)
        setattr(apply, attr, dest)  # redirect the patch at our temp copy

        try:
            getattr(apply, fn_name)()
        except SystemExit as e:
            failures.append(f"{fn_name}: PATCH FAILED -> {e}")
            continue

        result = subprocess.run(["node", "--check", str(dest)], capture_output=True, text=True)
        if result.returncode != 0:
            failures.append(f"{fn_name}: node --check failed\n{result.stderr.strip()}")
        else:
            print(f"ok   {fn_name}  ({live.name})")

    shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print(f"\nDRIFT DETECTED against Pi {version}:")
        for f in failures:
            print("  - " + f)
        print("\nFix the patches in scripts/apply.py, then run scripts/refresh_fixtures.py.")
        return 1

    print(f"\nNo drift: all patches apply cleanly to Pi {version} and produce valid JS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
