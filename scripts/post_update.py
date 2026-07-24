#!/usr/bin/env python3
"""Post-`pi update` handler for pi-local-mods.

Re-applies the patches to the freshly updated Pi and verifies them. On any
failure it prints a clean, copyable error report (step + the key detail + full
log path + exact re-run commands) instead of a raw traceback wall.

Invoked by scripts/pi-hook.sh after a successful `pi update`; also runnable
directly: `python3 scripts/post_update.py`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (label, command, copyable re-run)
STEPS = [
    ("apply.py - re-patching the updated Pi", [sys.executable, "scripts/apply.py"], "python3 scripts/apply.py"),
    ("smoke.py - drift check vs installed Pi", [sys.executable, "scripts/smoke.py"], "python3 scripts/smoke.py"),
    ("patch test suite", [sys.executable, "-m", "unittest", "scripts.test_apply"], "python3 -m unittest scripts.test_apply"),
]


def format_failure(label: str, rerun: str, log_path: str, captured: str, root: Path) -> str:
    """Build the copyable failure report. Pure/testable."""
    lines = [ln for ln in captured.splitlines() if ln.strip() and not ln.lstrip().startswith("==>")]
    detail = lines[-15:] if lines else ["(no output)"]
    out = [
        "┌─ pi-local-mods: re-apply after `pi update` FAILED ────────────────────────────────────",
        f"│ step: {label}",
        "│",
    ]
    out += [f"│ {ln}" for ln in detail]
    out += [
        "│",
        f"│ full log: {log_path}",
        "│",
        "│ to fix & re-verify:",
        f"│   cd {root} && {rerun}",
        "│ then, if you changed patches, refresh snapshots:",
        f"│   cd {root} && python3 scripts/refresh_fixtures.py",
        "└──────────────────────────────────────────────────────────────────────────────────────",
    ]
    return "\n".join(out)


def run() -> int:
    fd, name = tempfile.mkstemp(prefix="pi-local-mods-update-", suffix=".log")
    os.close(fd)
    log_path = Path(name)
    captured = ""
    for label, cmd, rerun in STEPS:
        captured += f"==> {label}\n"
        try:
            proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        except OSError as e:
            captured += f"Could not launch step: {e}\n"
            log_path.write_text(captured)
            sys.stderr.write(format_failure(label, rerun, str(log_path), captured, ROOT) + "\n")
            sys.stderr.write("\n(`pi update` itself succeeded; only the pi-local-mods re-apply failed.)\n")
            return 1
        captured += proc.stdout + proc.stderr
        log_path.write_text(captured)  # flush partial log so it's inspectable mid-run
        if proc.returncode != 0:
            sys.stderr.write(format_failure(label, rerun, str(log_path), captured, ROOT) + "\n")
            sys.stderr.write("\n(`pi update` itself succeeded; only the pi-local-mods re-apply failed.)\n")
            return proc.returncode
    sys.stderr.write("==> pi-local-mods: re-applied patches and verified (apply + smoke + tests OK).\n")
    sys.stderr.write("==> pi-local-mods: restart Pi to use the patched runtime.\n")
    try:
        log_path.unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
