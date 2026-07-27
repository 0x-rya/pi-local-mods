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

    # pi-lean-ctx is a two-file patch and must be validated atomically against
    # the currently installed package, including TypeScript syntax.
    live_lean_package = apply.LEAN_CTX_PACKAGE
    if live_lean_package.exists():
        lean_package = tmp / "pi-lean-ctx"
        lean_extensions = lean_package / "extensions"
        lean_extensions.mkdir(parents=True, exist_ok=True)
        lean_targets = [
            ("LEAN_CTX_INDEX", "index.ts"),
            ("LEAN_CTX_MCP_BRIDGE", "mcp-bridge.ts"),
        ]
        try:
            for attr, filename in lean_targets:
                live = getattr(apply, attr)
                src = apply.clean_source(live, apply.CLEAN_MARKERS[attr])
                dest = lean_extensions / filename
                shutil.copy2(src, dest)
                setattr(apply, attr, dest)
            apply.LEAN_CTX_PACKAGE = lean_package
            apply.patch_lean_ctx_session_cwd()
            for attr, filename in lean_targets:
                dest = getattr(apply, attr)
                result = subprocess.run(["node", "--check", str(dest)], capture_output=True, text=True)
                if result.returncode != 0:
                    failures.append(
                        f"patch_lean_ctx_session_cwd: node --check failed for {filename}\n"
                        f"{result.stderr.strip()}"
                    )
                else:
                    print(f"ok   patch_lean_ctx_session_cwd  ({filename})")
        except SystemExit as e:
            failures.append(f"patch_lean_ctx_session_cwd: PATCH FAILED -> {e}")

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
