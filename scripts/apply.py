#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()
PI_AGENT_DIR = HOME / ".pi" / "agent"
ROOT = Path(__file__).resolve().parents[1]


def find_pi_package() -> Path:
    override = os.environ.get("PI_CODING_AGENT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    try:
        npm_root = subprocess.check_output(["npm", "root", "-g"], text=True).strip()
        return Path(npm_root) / "@earendil-works" / "pi-coding-agent"
    except Exception:
        return HOME / ".nvm/versions/node/v24.4.1/lib/node_modules/@earendil-works/pi-coding-agent"


PI_PACKAGE = find_pi_package()
INTERACTIVE = PI_PACKAGE / "dist/modes/interactive/interactive-mode.js"
TERMINAL = PI_PACKAGE / "node_modules/@earendil-works/pi-tui/dist/terminal.js"

FIXED_BOTTOM_SCROLL_LAYOUT = r'''class FixedBottomScrollLayout {
    ui;
    scrollChildren;
    pinnedChildren;
    scrollOffset = 0;
    lastScrollableLineCount = 0;
    lastVisibleStart = 0;
    lastTranscriptRows = 1;
    lastTopPadding = 0;
    lastScrollLines = [];
    selection = undefined;
    selectionAutoCopy = /^(1|true|yes)$/i.test(process.env.PI_SELECTION_AUTO_COPY ?? "");
    constructor(ui, scrollChildren, pinnedChildren) {
        this.ui = ui;
        this.scrollChildren = scrollChildren;
        this.pinnedChildren = pinnedChildren;
    }
    invalidate() {
        for (const child of [...this.scrollChildren, ...this.pinnedChildren]) {
            child.invalidate?.();
        }
    }
    renderChildren(children, width) {
        const lines = [];
        for (const child of children) {
            lines.push(...child.render(width));
        }
        return lines;
    }
    maxScrollOffset(viewportRows) {
        return Math.max(0, this.lastScrollableLineCount - viewportRows);
    }
    scrollBy(rows) {
        const termRows = this.ui.terminal?.rows ?? 24;
        const pinnedRows = this.renderChildren(this.pinnedChildren, this.ui.terminal?.columns ?? 80).length;
        const viewportRows = Math.max(1, termRows - pinnedRows);
        this.scrollOffset = Math.max(0, Math.min(this.maxScrollOffset(viewportRows), this.scrollOffset + rows));
        this.ui.requestRender();
    }
    scrollToBottom() {
        if (this.scrollOffset !== 0) {
            this.scrollOffset = 0;
            this.ui.requestRender();
        }
    }
    preserveScrollAnchor(callback) {
        if (this.scrollOffset <= 0) {
            callback();
            this.ui.requestRender();
            return;
        }
        const width = this.ui.terminal?.columns ?? 80;
        const termRows = Math.max(1, this.ui.terminal?.rows ?? 24);
        const pinnedLines = this.renderChildren(this.pinnedChildren, width);
        const pinnedRows = Math.min(pinnedLines.length, termRows - 1);
        const transcriptRows = Math.max(1, termRows - pinnedRows);
        const oldLines = this.renderChildren(this.scrollChildren, width);
        const oldMaxStart = Math.max(0, oldLines.length - transcriptRows);
        const oldStart = Math.max(0, oldMaxStart - this.scrollOffset);
        const anchorRow = oldStart + 1 < oldLines.length ? 1 : 0;
        const anchorIndex = oldStart + anchorRow;
        const anchorLine = oldLines[anchorIndex];
        callback();
        const newLines = this.renderChildren(this.scrollChildren, width);
        this.lastScrollableLineCount = newLines.length;
        const newMaxStart = Math.max(0, newLines.length - transcriptRows);
        let newAnchorIndex = -1;
        if (anchorLine !== undefined) {
            for (let i = 0; i < newLines.length; i++) {
                if (newLines[i] !== anchorLine)
                    continue;
                if (newAnchorIndex === -1 || Math.abs(i - anchorIndex) < Math.abs(newAnchorIndex - anchorIndex)) {
                    newAnchorIndex = i;
                }
            }
        }
        const newStart = newAnchorIndex === -1
            ? Math.min(oldStart, newMaxStart)
            : Math.max(0, Math.min(newAnchorIndex - anchorRow, newMaxStart));
        this.scrollOffset = Math.max(0, Math.min(newMaxStart - newStart, this.maxScrollOffset(transcriptRows)));
        this.ui.requestRender();
    }
    stripAnsi(text) {
        return text.replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "").replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b_[\s\S]*?(?:\x07|\x1b\\)/g, "");
    }
    positionFromMouse(x, y) {
        const row = y - 1;
        if (row < 0 || row >= this.lastTranscriptRows) {
            return undefined;
        }
        const visibleRow = row - this.lastTopPadding;
        if (visibleRow < 0) {
            return undefined;
        }
        if (this.scrollOffset > 0 && visibleRow === 0) {
            return undefined;
        }
        const line = this.lastVisibleStart + visibleRow;
        if (line < 0 || line >= this.lastScrollableLineCount) {
            return undefined;
        }
        return { line, col: Math.max(0, x - 1) };
    }
    normalizedSelection() {
        if (!this.selection)
            return undefined;
        const { anchor, focus } = this.selection;
        if (anchor.line < focus.line || (anchor.line === focus.line && anchor.col <= focus.col)) {
            return { start: anchor, end: focus };
        }
        return { start: focus, end: anchor };
    }
    getSelectedText() {
        const range = this.normalizedSelection();
        if (!range)
            return "";
        const lines = [];
        for (let lineIndex = range.start.line; lineIndex <= range.end.line; lineIndex++) {
            const plain = this.stripAnsi(this.lastScrollLines[lineIndex] ?? "");
            const startCol = lineIndex === range.start.line ? range.start.col : 0;
            const endCol = lineIndex === range.end.line ? range.end.col : visibleWidth(plain);
            const width = Math.max(0, endCol - startCol);
            lines.push(sliceByColumn(plain, startCol, width, true));
        }
        return lines.join("\n").replace(/[ \t]+$/gm, "").replace(/^\n+|\n+$/g, "");
    }
    copySelection() {
        const text = this.getSelectedText();
        if (!text)
            return false;
        void copyToClipboard(text);
        return true;
    }
    startSelection(pos) {
        this.selection = { anchor: pos, focus: pos, dragging: true };
        this.ui.requestRender();
    }
    updateSelection(pos) {
        if (!this.selection)
            return;
        this.selection = { ...this.selection, focus: pos };
        this.ui.requestRender();
    }
    finishSelection() {
        if (!this.selection)
            return;
        this.selection = { ...this.selection, dragging: false };
        if (this.selectionAutoCopy) {
            this.copySelection();
        }
        this.ui.requestRender();
    }
    applySelectionToLine(line, absoluteLineIndex) {
        const range = this.normalizedSelection();
        if (!range || absoluteLineIndex < range.start.line || absoluteLineIndex > range.end.line) {
            return line;
        }
        const lineWidth = visibleWidth(line);
        const startCol = absoluteLineIndex === range.start.line ? Math.min(range.start.col, lineWidth) : 0;
        const endCol = absoluteLineIndex === range.end.line ? Math.min(range.end.col, lineWidth) : lineWidth;
        if (endCol <= startCol) {
            return line;
        }
        const before = sliceByColumn(line, 0, startCol, true);
        const selected = sliceByColumn(line, startCol, endCol - startCol, true);
        const after = sliceByColumn(line, endCol, Math.max(0, lineWidth - endCol), true);
        return `${before}\x1b[7m${selected}\x1b[27m${after}`;
    }
    handleMouse(data) {
        const mouseMatch = data.match(/^\x1b\[<(\d+);(\d+);(\d+)([mM])$/);
        if (!mouseMatch)
            return undefined;
        const button = Number(mouseMatch[1]);
        const x = Number(mouseMatch[2]);
        const y = Number(mouseMatch[3]);
        const eventType = mouseMatch[4];
        if (eventType === "M" && (button & 64) !== 0) {
            const wheelDirection = button & 3;
            if (wheelDirection === 0) {
                this.scrollBy(3);
                return { consume: true };
            }
            if (wheelDirection === 1) {
                this.scrollBy(-3);
                return { consume: true };
            }
        }
        if (eventType === "M" && (button & 32) !== 0 && this.selection?.dragging) {
            if (y <= 2) {
                this.scrollBy(2);
            }
            else if (y >= (this.ui.terminal?.rows ?? 24) - 1) {
                this.scrollBy(-2);
            }
            const pos = this.positionFromMouse(x, y);
            if (pos)
                this.updateSelection(pos);
            return { consume: true };
        }
        if (eventType === "M" && (button & 3) === 0) {
            const pos = this.positionFromMouse(x, y);
            if (pos) {
                this.startSelection(pos);
                return { consume: true };
            }
        }
        if (eventType === "m") {
            this.finishSelection();
            return { consume: true };
        }
        return undefined;
    }
    handleInput(data) {
        const mouseResult = this.handleMouse(data);
        if (mouseResult)
            return mouseResult;
        if (this.selection && matchesKey(data, "ctrl+x")) {
            if (this.copySelection()) {
                return { consume: true };
            }
        }
        if (this.selection && matchesKey(data, "escape")) {
            this.selection = undefined;
            this.ui.requestRender();
            return { consume: true };
        }
        const termRows = this.ui.terminal?.rows ?? 24;
        const page = Math.max(3, Math.floor(termRows * 0.7));
        if (matchesKey(data, "pageUp") || matchesKey(data, "shift+pageUp")) {
            this.scrollBy(page);
            return { consume: true };
        }
        if (matchesKey(data, "pageDown") || matchesKey(data, "shift+pageDown")) {
            this.scrollBy(-page);
            return { consume: true };
        }
        if (matchesKey(data, "alt+up")) {
            this.scrollBy(5);
            return { consume: true };
        }
        if (matchesKey(data, "alt+down")) {
            this.scrollBy(-5);
            return { consume: true };
        }
        if (matchesKey(data, "home") || matchesKey(data, "shift+alt+left") || matchesKey(data, "shift+alt+up")) {
            this.scrollBy(Number.MAX_SAFE_INTEGER);
            return { consume: true };
        }
        if ((matchesKey(data, "end") || matchesKey(data, "shift+alt+right") || matchesKey(data, "shift+alt+down")) && this.scrollOffset > 0) {
            this.scrollToBottom();
            return { consume: true };
        }
        return undefined;
    }
    render(width) {
        const termRows = Math.max(1, this.ui.terminal?.rows ?? 24);
        const pinnedLines = this.renderChildren(this.pinnedChildren, width);
        const pinnedRows = Math.min(pinnedLines.length, termRows - 1);
        const visiblePinned = pinnedLines.slice(Math.max(0, pinnedLines.length - pinnedRows));
        let transcriptRows = Math.max(1, termRows - visiblePinned.length);
        const previousScrollableLineCount = this.lastScrollableLineCount;
        const scrollLines = this.renderChildren(this.scrollChildren, width);
        this.lastScrollLines = scrollLines;
        if (this.scrollOffset > 0 && scrollLines.length > previousScrollableLineCount) {
            this.scrollOffset += scrollLines.length - previousScrollableLineCount;
        }
        this.lastScrollableLineCount = scrollLines.length;
        this.scrollOffset = Math.max(0, Math.min(this.scrollOffset, this.maxScrollOffset(transcriptRows)));
        const maxStart = Math.max(0, scrollLines.length - transcriptRows);
        const start = Math.max(0, maxStart - this.scrollOffset);
        this.lastVisibleStart = start;
        this.lastTranscriptRows = transcriptRows;
        let visibleScroll = scrollLines.slice(start, start + transcriptRows);
        this.lastTopPadding = Math.max(0, transcriptRows - visibleScroll.length);
        visibleScroll = visibleScroll.map((line, idx) => this.applySelectionToLine(line, start + idx));
        if (this.scrollOffset > 0 && visibleScroll.length > 0) {
            const marker = theme.fg("warning", `↑ scrolled ${this.scrollOffset} lines`) + theme.fg("dim", " · Opt+↓/End to bottom");
            visibleScroll[0] = marker;
        }
        if (this.lastTopPadding > 0) {
            visibleScroll = [...Array(this.lastTopPadding).fill(""), ...visibleScroll];
        }
        const lines = [...visibleScroll, ...visiblePinned];
        return lines.slice(Math.max(0, lines.length - termRows));
    }
}'''


def backup(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Missing expected file: {path}")
    bak = path.with_suffix(path.suffix + ".pi-local-mods.bak")
    if not bak.exists():
        shutil.copy2(path, bak)


def patch_interactive() -> None:
    backup(INTERACTIVE)
    text = INTERACTIVE.read_text()
    text = text.replace(
        'TUI, visibleWidth, } from "@earendil-works/pi-tui";',
        'TUI, visibleWidth, sliceByColumn, } from "@earendil-works/pi-tui";',
    )
    if 'sliceByColumn, } from "@earendil-works/pi-tui";' not in text:
        raise SystemExit("Could not patch pi-tui import in interactive-mode.js")
    start = text.index("class FixedBottomScrollLayout {")
    end = text.index("\nfunction isCustomSessionEntry", start)
    INTERACTIVE.write_text(text[:start] + FIXED_BOTTOM_SCROLL_LAYOUT + text[end:])


def patch_terminal() -> None:
    backup(TERMINAL)
    text = TERMINAL.read_text()
    # Normalize any previous mouse-mode patch back to our desired mode.
    text = text.replace('process.stdout.write("\\x1b[?1000h\\x1b[?1006h");', 'process.stdout.write("\\x1b[?1002h\\x1b[?1006h");')
    text = text.replace('process.stdout.write("\\x1b[?1000l\\x1b[?1006l");', 'process.stdout.write("\\x1b[?1002l\\x1b[?1006l");')
    if 'process.stdout.write("\\x1b[?1002h\\x1b[?1006h");' not in text:
        needle = '        // Enable bracketed paste mode - terminal will wrap pastes in \\x1b[200~ ... \\x1b[201~\n        process.stdout.write("\\x1b[?2004h");'
        repl = needle + '\n        // Enable button-event mouse tracking with SGR encoding for wheel /\n        // trackpad scroll gestures and app-owned transcript selection.\n        process.stdout.write("\\x1b[?1002h\\x1b[?1006h");'
        text = text.replace(needle, repl)
    if 'process.stdout.write("\\x1b[?1002l\\x1b[?1006l");' not in text:
        needle = '        // Disable bracketed paste mode\n        process.stdout.write("\\x1b[?2004l");'
        repl = '        // Disable mouse tracking and bracketed paste mode\n        process.stdout.write("\\x1b[?1002l\\x1b[?1006l");\n        process.stdout.write("\\x1b[?2004l");'
        text = text.replace(needle, repl)
    TERMINAL.write_text(text)


def install_theme() -> None:
    theme_dir = PI_AGENT_DIR / "themes"
    theme_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "themes" / "codex-dark.json", theme_dir / "codex-dark.json")

    settings_path = PI_AGENT_DIR / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}
    settings["theme"] = "codex-dark"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


def verify() -> None:
    for path in (INTERACTIVE, TERMINAL):
        subprocess.run(["node", "--check", str(path)], check=True)


def main() -> None:
    patch_interactive()
    patch_terminal()
    install_theme()
    verify()
    print("Applied pi-local-mods. Restart pi to use the patched runtime.")


if __name__ == "__main__":
    main()
