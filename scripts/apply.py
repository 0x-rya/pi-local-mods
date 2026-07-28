#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
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
CLIPBOARD_IMAGE = PI_PACKAGE / "dist/utils/clipboard-image.js"
FOOTER = PI_PACKAGE / "dist/modes/interactive/components/footer.js"
CUSTOM_EDITOR = PI_PACKAGE / "dist/modes/interactive/components/custom-editor.js"
TERMINAL = PI_PACKAGE / "node_modules/@earendil-works/pi-tui/dist/terminal.js"
TUI_JS = PI_PACKAGE / "node_modules/@earendil-works/pi-tui/dist/tui.js"
BG_TASKS_PACKAGE = PI_AGENT_DIR / "npm/node_modules/pi-patty-bg-tasks"
BG_TASKS_SHORTCUTS = BG_TASKS_PACKAGE / "src/shortcuts.ts"
BG_TASKS_HINT = BG_TASKS_PACKAGE / "src/hint.ts"
LEAN_CTX_PACKAGE = PI_AGENT_DIR / "npm/node_modules/pi-lean-ctx"
LEAN_CTX_INDEX = LEAN_CTX_PACKAGE / "extensions/index.ts"
LEAN_CTX_MCP_BRIDGE = LEAN_CTX_PACKAGE / "extensions/mcp-bridge.ts"
QUOTA_DASHBOARD_SRC = ROOT / "extensions" / "quota-dashboard.ts"
QUOTA_DASHBOARD_DST = PI_AGENT_DIR / "extensions" / "quota-dashboard.ts"

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
    chatContainer;
    messageSpans = [];
    topMessageTarget;
    topMessagePreview = "";
    bottomMessageTarget;
    bottomMessagePreview = "";
    lastTopBarRow = -1;
    lastBottomBarRow = -1;
    constructor(ui, scrollChildren, pinnedChildren, chatContainer) {
        this.ui = ui;
        this.scrollChildren = scrollChildren;
        this.pinnedChildren = pinnedChildren;
        // chatContainer is scrollChildren[2]; the explicit arg lets future
        // callers pass it directly. It maps transcript lines back to messages
        // for the pinned "previous message" jump bar.
        this.chatContainer = chatContainer ?? scrollChildren[2];
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
    // Render the scroll children, recording the line span of each chat message
    // so the top "previous message" bar can preview/jump to it. Container.render
    // is a pure concat of child.render(), so iterating chatContainer.children
    // reproduces the exact same lines as chatContainer.render(width).
    renderScrollLinesWithSpans(width) {
        const lines = [];
        const spans = [];
        for (const child of this.scrollChildren) {
            if (child === this.chatContainer && Array.isArray(child.children)) {
                for (const grandChild of child.children) {
                    const childLines = grandChild.render(width);
                    const startLine = lines.length;
                    // Only user messages are jump targets for the top bar.
                    if (grandChild instanceof UserMessageComponent) {
                        const preview = this.firstMeaningfulLine(childLines);
                        if (preview) {
                            spans.push({ start: startLine, end: startLine + childLines.length - 1, preview });
                        }
                    }
                    for (const line of childLines) {
                        lines.push(line);
                    }
                }
            }
            else {
                const childLines = child.render(width);
                for (const line of childLines) {
                    lines.push(line);
                }
            }
        }
        this.messageSpans = spans;
        return lines;
    }
    firstMeaningfulLine(childLines) {
        for (const raw of childLines) {
            const plain = this.stripAnsi(raw).trim();
            if (plain && /\p{L}|\p{N}/u.test(plain)) {
                return plain;
            }
        }
        return "";
    }
    findPreviousMessage(spans, startLine) {
        let prev = undefined;
        for (const span of spans) {
            if (span.start < startLine && (!prev || span.start > prev.start)) {
                prev = span;
            }
        }
        return prev;
    }
    findNextMessage(spans, threshold) {
        let next = undefined;
        for (const span of spans) {
            if (span.start >= threshold && (!next || span.start < next.start)) {
                next = span;
            }
        }
        return next;
    }
    scrollToMessageStart(targetStart) {
        const width = this.ui.terminal?.columns ?? 80;
        const termRows = Math.max(1, this.ui.terminal?.rows ?? 24);
        const pinnedLines = this.renderChildren(this.pinnedChildren, width);
        const pinnedRows = Math.min(pinnedLines.length, termRows - 1);
        const visiblePinned = pinnedLines.slice(Math.max(0, pinnedLines.length - pinnedRows));
        const transcriptRows = Math.max(1, termRows - visiblePinned.length);
        const scrollLines = this.renderChildren(this.scrollChildren, width);
        const maxStart = Math.max(0, scrollLines.length - transcriptRows);
        // Land the target message's first line just below the top marker.
        const newStart = Math.max(0, Math.min(targetStart - 1, maxStart));
        this.scrollOffset = Math.max(0, Math.min(maxStart - newStart, this.maxScrollOffset(transcriptRows)));
        this.ui.requestRender();
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
            // Click on a pinned message bar → jump to that message.
            const row = y - 1;
            if (this.topMessageTarget != null && row === this.lastTopBarRow) {
                this.scrollToMessageStart(this.topMessageTarget);
                return { consume: true };
            }
            if (this.bottomMessageTarget != null && row === this.lastBottomBarRow) {
                this.scrollToMessageStart(this.bottomMessageTarget);
                return { consume: true };
            }
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
        const scrollLines = this.renderScrollLinesWithSpans(width);
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
        this.topMessageTarget = undefined;
        this.topMessagePreview = "";
        this.bottomMessageTarget = undefined;
        this.bottomMessagePreview = "";
        this.lastTopBarRow = -1;
        this.lastBottomBarRow = -1;
        // Lines above the viewport = start; lines below = scrollOffset (newer
        // content hidden underneath). The top bar reports above, the bottom bar
        // below — so each arrow points at the content it describes.
        const aboveCount = start;
        const belowCount = this.scrollOffset;
        const aboveLead = aboveCount > 0 ? `${aboveCount}↑` : "↑";
        const viewportTopContentLine = start + (this.scrollOffset > 0 ? 1 : 0);
        const prev = this.findPreviousMessage(this.messageSpans, viewportTopContentLine);
        if (prev && visibleScroll.length > 0) {
            this.topMessageTarget = prev.start;
            this.topMessagePreview = prev.preview;
            this.lastTopBarRow = this.lastTopPadding;
            const bottomHint = this.scrollOffset > 0 ? " · Opt+↓/End to bottom" : "";
            const topSuffix = ` · click to jump${bottomHint}`;
            // Budget the preview against the prefix (lead + separator) and the
            // suffix so the assembled bar can never exceed the terminal width.
            const topAvail = Math.max(0, width - (visibleWidth(aboveLead) + 1) - visibleWidth(topSuffix));
            const snippet = truncateToWidth(prev.preview, topAvail, theme.fg("dim", "…"));
            let topLine = theme.fg("accent", aboveLead) + " " + theme.fg("muted", snippet) + theme.fg("dim", topSuffix);
            if (visibleWidth(topLine) > width) {
                topLine = truncateToWidth(topLine, width, theme.fg("dim", "…"));
            }
            visibleScroll[0] = topLine;
        }
        else if (this.scrollOffset > 0 && visibleScroll.length > 0) {
            visibleScroll[0] = theme.fg("warning", aboveLead) + theme.fg("dim", " · Opt+↓/End to bottom");
        }
        // Bottom sticky bar: next user message below the viewport (scrolled only).
        if (this.scrollOffset > 0 && visibleScroll.length > 1) {
            const nextThreshold = start + visibleScroll.length - 1;
            const next = this.findNextMessage(this.messageSpans, nextThreshold);
            const belowTag = `${belowCount}↓`;
            this.lastBottomBarRow = this.lastTopPadding + (visibleScroll.length - 1);
            if (next) {
                this.bottomMessageTarget = next.start;
                this.bottomMessagePreview = next.preview;
                const bottomSuffix = " · click to jump";
                const bottomAvail = Math.max(0, width - (visibleWidth(belowTag) + 1) - visibleWidth(bottomSuffix));
                const snippet = truncateToWidth(next.preview, bottomAvail, theme.fg("dim", "…"));
                let bottomLine = theme.fg("accent", belowTag) + " " + theme.fg("muted", snippet) + theme.fg("dim", bottomSuffix);
                if (visibleWidth(bottomLine) > width) {
                    bottomLine = truncateToWidth(bottomLine, width, theme.fg("dim", "…"));
                }
                visibleScroll[visibleScroll.length - 1] = bottomLine;
            }
            else {
                // No user message below, but newer content still exists below.
                visibleScroll[visibleScroll.length - 1] = theme.fg("warning", belowTag) + theme.fg("dim", " · Opt+↓/End to bottom");
            }
        }
        if (this.lastTopPadding > 0) {
            visibleScroll = [...Array(this.lastTopPadding).fill(""), ...visibleScroll];
        }
        const lines = [...visibleScroll, ...visiblePinned];
        return lines.slice(Math.max(0, lines.length - termRows));
    }
}'''


TERMINAL_LOG_GUARD_METHODS = r'''    installTerminalOutputGuard() {
        if (this.terminalOutputGuard) {
            return;
        }
        const originalStderrWrite = process.stderr.write;
        const originalConsoleError = console.error;
        const originalConsoleWarn = console.warn;
        const originalConsoleLog = console.log;
        const capture = (source, args) => {
            this.captureTerminalLog(source, `${formatConsoleArgs(...args)}\n`);
        };
        const stderrWrite = ((chunk, encodingOrCallback, callback) => {
            this.captureTerminalLog("stderr", Buffer.isBuffer(chunk) ? chunk.toString(typeof encodingOrCallback === "string" ? encodingOrCallback : "utf8") : String(chunk));
            const cb = typeof encodingOrCallback === "function" ? encodingOrCallback : callback;
            if (cb) {
                process.nextTick(cb);
            }
            return true;
        });
        const consoleError = (...args) => capture("console.error", args);
        const consoleWarn = (...args) => capture("console.warn", args);
        const consoleLog = (...args) => capture("console.log", args);
        process.stderr.write = stderrWrite;
        console.error = consoleError;
        console.warn = consoleWarn;
        console.log = consoleLog;
        this.terminalOutputGuard = {
            originalStderrWrite,
            originalConsoleError,
            originalConsoleWarn,
            originalConsoleLog,
            stderrWrite,
            consoleError,
            consoleWarn,
            consoleLog,
        };
    }
    uninstallTerminalOutputGuard(options = {}) {
        const guard = this.terminalOutputGuard;
        if (!guard) {
            return;
        }
        if (this.capturedTerminalLogRenderTimer) {
            clearTimeout(this.capturedTerminalLogRenderTimer);
            this.capturedTerminalLogRenderTimer = undefined;
        }
        this.flushCapturedTerminalLogPartials(options.render !== false);
        if (process.stderr.write === guard.stderrWrite) {
            process.stderr.write = guard.originalStderrWrite;
        }
        if (console.error === guard.consoleError) {
            console.error = guard.originalConsoleError;
        }
        if (console.warn === guard.consoleWarn) {
            console.warn = guard.originalConsoleWarn;
        }
        if (console.log === guard.consoleLog) {
            console.log = guard.originalConsoleLog;
        }
        this.terminalOutputGuard = undefined;
    }
    sanitizeCapturedTerminalLog(text) {
        return text
            .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
            .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
            .replace(/\x1b[_^PX][\s\S]*?(?:\x07|\x1b\\)/g, "")
            .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
    }
    addCapturedTerminalLogLine(source, line) {
        const trimmed = line.trimEnd();
        if (trimmed.length === 0) {
            return false;
        }
        this.capturedTerminalLogs.push({
            id: this.capturedTerminalLogNextId++,
            source,
            text: trimmed,
            expanded: false,
        });
        const maxStored = 50;
        if (this.capturedTerminalLogs.length > maxStored) {
            this.capturedTerminalLogs.splice(0, this.capturedTerminalLogs.length - maxStored);
        }
        return true;
    }
    captureTerminalLog(source, text) {
        if (!this.isInitialized && !this.fixedLayout) {
            return;
        }
        const sanitized = this.sanitizeCapturedTerminalLog(text).replace(/\r/g, "\n");
        const combined = (this.capturedTerminalLogPartials.get(source) ?? "") + sanitized;
        const parts = combined.split("\n");
        let partial = parts.pop() ?? "";
        let changed = false;
        for (const part of parts) {
            changed = this.addCapturedTerminalLogLine(source, part) || changed;
        }
        if (partial.length > 4000) {
            changed = this.addCapturedTerminalLogLine(source, partial) || changed;
            partial = "";
        }
        if (partial) {
            this.capturedTerminalLogPartials.set(source, partial);
        }
        else {
            this.capturedTerminalLogPartials.delete(source);
        }
        if (changed) {
            this.scheduleCapturedTerminalLogRender();
        }
    }
    flushCapturedTerminalLogPartials(render = true) {
        let changed = false;
        for (const [source, partial] of this.capturedTerminalLogPartials) {
            changed = this.addCapturedTerminalLogLine(source, partial) || changed;
        }
        this.capturedTerminalLogPartials.clear();
        if (changed && render) {
            this.renderCapturedTerminalLogs();
        }
    }
    scheduleCapturedTerminalLogRender() {
        if (this.capturedTerminalLogRenderTimer) {
            return;
        }
        this.capturedTerminalLogRenderTimer = setTimeout(() => {
            this.capturedTerminalLogRenderTimer = undefined;
            this.renderCapturedTerminalLogs();
        }, 50);
    }
    wrapCapturedTerminalLogLine(text, width) {
        const lines = [];
        let remaining = text;
        while (visibleWidth(remaining) > width) {
            lines.push(sliceByColumn(remaining, 0, width, true));
            remaining = sliceByColumn(remaining, width, Math.max(0, visibleWidth(remaining) - width), true);
        }
        lines.push(remaining);
        return lines;
    }
    removeCapturedTerminalLog(id) {
        this.capturedTerminalLogs = this.capturedTerminalLogs.filter((entry) => entry.id !== id);
        this.renderCapturedTerminalLogs();
    }
    toggleCapturedTerminalLog(id) {
        const entry = this.capturedTerminalLogs.find((item) => item.id === id);
        if (entry) {
            entry.expanded = !entry.expanded;
            this.renderCapturedTerminalLogs();
        }
    }
    copyCapturedTerminalLog(id) {
        const entry = this.capturedTerminalLogs.find((item) => item.id === id);
        if (entry) {
            void copyToClipboard(`[${entry.source}] ${entry.text}`);
        }
    }
    clearCapturedTerminalLogs() {
        this.capturedTerminalLogs = [];
        this.capturedTerminalLogPartials.clear();
        this.renderCapturedTerminalLogs();
    }
    handleCapturedTerminalLogInput(data) {
        const mouseMatch = data.match(/^\x1b\[<(\d+);(\d+);(\d+)([mM])$/);
        if (!mouseMatch || mouseMatch[4] !== "M") {
            return undefined;
        }
        const button = Number(mouseMatch[1]);
        if ((button & 3) !== 0 || (button & 64) !== 0) {
            return undefined;
        }
        if (!this.capturedTerminalLogComponent || !this.fixedLayout) {
            return undefined;
        }
        const x = Number(mouseMatch[2]) - 1;
        const y = Number(mouseMatch[3]) - 1;
        const width = this.ui.terminal?.columns ?? 80;
        const termRows = Math.max(1, this.ui.terminal?.rows ?? 24);
        const pinnedLines = this.fixedLayout.renderChildren(this.fixedLayout.pinnedChildren, width);
        const pinnedRows = Math.min(pinnedLines.length, termRows - 1);
        const visiblePinnedStart = Math.max(0, pinnedLines.length - pinnedRows);
        const localRow = y - (termRows - pinnedRows) + visiblePinnedStart;
        const hitCandidates = this.capturedTerminalLogHitRegions.filter((region) => region.row === localRow && x >= region.startCol && x < region.endCol);
        const priority = { copy: 0, close: 1, clear: 1, toggle: 2 };
        const hit = hitCandidates.sort((a, b) => (priority[a.type] ?? 99) - (priority[b.type] ?? 99))[0];
        if (!hit) {
            return undefined;
        }
        if (hit.type === "clear") {
            this.clearCapturedTerminalLogs();
        }
        else if (hit.type === "close") {
            this.removeCapturedTerminalLog(hit.id);
        }
        else if (hit.type === "copy") {
            this.copyCapturedTerminalLog(hit.id);
        }
        else if (hit.type === "toggle") {
            this.toggleCapturedTerminalLog(hit.id);
        }
        return { consume: true };
    }
    renderCapturedTerminalLogs() {
        this.terminalLogContainer.clear();
        if (this.capturedTerminalLogs.length === 0) {
            this.capturedTerminalLogComponent = undefined;
            this.capturedTerminalLogHitRegions = [];
            this.ui.requestRender();
            return;
        }
        const getLogs = () => this.capturedTerminalLogs.slice();
        this.capturedTerminalLogComponent = {
            render: (width) => {
                this.capturedTerminalLogHitRegions = [];
                if (width <= 0) {
                    return [];
                }
                const fit = (line) => visibleWidth(line) > width ? sliceByColumn(line, 0, width, true) : line;
                const logs = getLogs();
                const maxShown = 8;
                const shown = logs.slice(-maxShown);
                const hidden = Math.max(0, logs.length - shown.length);
                const closeAll = width >= 8 ? " [×]" : "";
                const title = `Captured terminal logs (${shown.length}${hidden ? ` shown, ${hidden} hidden` : ""})`;
                const titleWidth = Math.max(0, width - visibleWidth(closeAll));
                const truncatedTitle = visibleWidth(title) > titleWidth ? (titleWidth <= 1 ? "…" : `${sliceByColumn(title, 0, titleWidth - 1, true)}…`) : title;
                const header = theme.fg("warning", truncatedTitle) + theme.fg("dim", closeAll);
                if (closeAll) {
                    const headerCloseStart = visibleWidth(truncatedTitle) + 1;
                    this.capturedTerminalLogHitRegions.push({ type: "clear", row: 0, startCol: headerCloseStart, endCol: Math.min(width, headerCloseStart + 3) });
                }
                const lines = [fit(header)];
                let row = 1;
                for (const entry of shown) {
                    if (entry.expanded) {
                        const controls = "× ▾ [copy] ";
                        const head = `${entry.source}: ${entry.text}`;
                        const headAvailable = Math.max(0, width - visibleWidth(controls));
                        const headText = visibleWidth(head) > headAvailable ? (headAvailable <= 1 ? "…" : `${sliceByColumn(head, 0, headAvailable - 1, true)}…`) : head;
                        lines.push(fit(theme.fg("dim", "×") + " " + theme.fg("warning", "▾") + " " + theme.fg("accent", "[copy]") + " " + theme.fg("warning", headText)));
                        this.capturedTerminalLogHitRegions.push({ type: "close", id: entry.id, row, startCol: 0, endCol: 1 });
                        this.capturedTerminalLogHitRegions.push({ type: "toggle", id: entry.id, row, startCol: 2, endCol: width });
                        this.capturedTerminalLogHitRegions.push({ type: "copy", id: entry.id, row, startCol: 4, endCol: 10 });
                        row++;
                        const bodyPrefix = "  │ ";
                        const bodyWidth = Math.max(1, width - visibleWidth(bodyPrefix));
                        for (const wrapped of this.wrapCapturedTerminalLogLine(entry.text, bodyWidth)) {
                            lines.push(fit(theme.fg("dim", bodyPrefix) + theme.fg("warning", wrapped)));
                            this.capturedTerminalLogHitRegions.push({ type: "toggle", id: entry.id, row, startCol: 0, endCol: width });
                            row++;
                        }
                    }
                    else {
                        const controls = "× ▸ ";
                        const text = `${entry.source}: ${entry.text}`;
                        const available = Math.max(0, width - visibleWidth(controls));
                        const truncated = visibleWidth(text) > available ? (available <= 1 ? "…" : `${sliceByColumn(text, 0, available - 1, true)}…`) : text;
                        lines.push(fit(theme.fg("dim", "×") + " " + theme.fg("warning", "▸") + " " + theme.fg("warning", truncated)));
                        this.capturedTerminalLogHitRegions.push({ type: "close", id: entry.id, row, startCol: 0, endCol: 1 });
                        this.capturedTerminalLogHitRegions.push({ type: "toggle", id: entry.id, row, startCol: 2, endCol: width });
                        row++;
                    }
                }
                return lines;
            },
            invalidate: () => { },
        };
        this.terminalLogContainer.addChild(this.capturedTerminalLogComponent);
        this.ui.requestRender();
    }
'''


def patch_terminal_log_guard(text: str) -> str:
    if 'import { format as formatConsoleArgs } from "node:util";' not in text:
        text = text.replace('import * as path from "node:path";', 'import * as path from "node:path";\nimport { format as formatConsoleArgs } from "node:util";')
    if 'terminalLogContainer;' not in text:
        text = text.replace('    pendingMessagesContainer;\n    statusContainer;', '    pendingMessagesContainer;\n    terminalLogContainer;\n    statusContainer;')
    if 'capturedTerminalLogs = [];' not in text:
        text = text.replace(
            '    // Extension UI state\n    extensionSelector = undefined;',
            '    // Captured terminal logs (stderr/console) rendered through the TUI so raw logs cannot cover the editor/footer.\n'
            '    capturedTerminalLogs = [];\n'
            '    capturedTerminalLogNextId = 1;\n'
            '    capturedTerminalLogComponent = undefined;\n'
            '    capturedTerminalLogHitRegions = [];\n'
            '    capturedTerminalLogPartials = new Map();\n'
            '    capturedTerminalLogRenderTimer = undefined;\n'
            '    terminalOutputGuard = undefined;\n'
            '    // Extension UI state\n    extensionSelector = undefined;'
        )
    if 'capturedTerminalLogNextId = 1;' not in text:
        text = text.replace('    capturedTerminalLogs = [];\n    capturedTerminalLogComponent = undefined;\n    capturedTerminalLogPartials = new Map();', '    capturedTerminalLogs = [];\n    capturedTerminalLogNextId = 1;\n    capturedTerminalLogComponent = undefined;\n    capturedTerminalLogHitRegions = [];\n    capturedTerminalLogPartials = new Map();')
    if 'this.terminalLogContainer = new Container();' not in text:
        text = text.replace('        this.chatContainer = new Container();\n        this.pendingMessagesContainer = new Container();\n        this.statusContainer = new Container();', '        this.chatContainer = new Container();\n        this.pendingMessagesContainer = new Container();\n        this.terminalLogContainer = new Container();\n        this.statusContainer = new Container();')
    text = text.replace(
        '        ], [\n            this.statusContainer,\n            this.widgetContainerAbove,',
        '        ], [\n            this.terminalLogContainer,\n            this.statusContainer,\n            this.widgetContainerAbove,'
    )
    if 'this.installTerminalOutputGuard();\n        this.ui.start();' not in text:
        text = text.replace('        // Start the UI before initializing extensions so session_start handlers can use interactive dialogs\n        this.ui.start();', '        // Start the UI before initializing extensions so session_start handlers can use interactive dialogs\n        this.installTerminalOutputGuard();\n        this.ui.start();')
    if 'this.ui.addInputListener((data) => this.handleCapturedTerminalLogInput(data));' not in text:
        text = text.replace('        this.ui.addInputListener((data) => this.fixedLayout?.handleInput(data));', '        this.ui.addInputListener((data) => this.fixedLayout?.handleInput(data));\n        this.ui.addInputListener((data) => this.handleCapturedTerminalLogInput(data));')
    if 'this.uninstallTerminalOutputGuard();\n            this.ui.stop();' not in text:
        text = text.replace('            // Stop TUI to release terminal\n            this.ui.stop();', '            // Stop TUI to release terminal\n            this.uninstallTerminalOutputGuard();\n            this.ui.stop();')
    if 'this.installTerminalOutputGuard();\n            this.ui.start();' not in text:
        text = text.replace('            // Restart TUI\n            this.ui.start();', '            // Restart TUI\n            this.installTerminalOutputGuard();\n            this.ui.start();')
    if 'this.uninstallTerminalOutputGuard({ render: false });\n        console.error("pi exiting due to uncaughtException:");' not in text:
        text = text.replace('        console.error("pi exiting due to uncaughtException:");', '        this.uninstallTerminalOutputGuard({ render: false });\n        console.error("pi exiting due to uncaughtException:");')
    if 'installTerminalOutputGuard() {' in text:
        guard_start = text.index('    installTerminalOutputGuard() {')
        guard_end = text.index('    showNewVersionNotification(release) {', guard_start)
        text = text[:guard_start] + TERMINAL_LOG_GUARD_METHODS + text[guard_end:]
    else:
        text = text.replace(
            '    showWarning(warningMessage) {\n        this.chatContainer.addChild(new Spacer(1));\n        this.chatContainer.addChild(new Text(theme.fg("warning", `Warning: ${warningMessage}`), 1, 0));\n        this.ui.requestRender();\n    }\n    showNewVersionNotification(release) {',
            '    showWarning(warningMessage) {\n        this.chatContainer.addChild(new Spacer(1));\n        this.chatContainer.addChild(new Text(theme.fg("warning", `Warning: ${warningMessage}`), 1, 0));\n        this.ui.requestRender();\n    }\n'
            + TERMINAL_LOG_GUARD_METHODS
            + '    showNewVersionNotification(release) {'
        )
    if 'this.uninstallTerminalOutputGuard();\n        if (this.settingsManager.getShowTerminalProgress()) {' not in text:
        text = text.replace('        if (this.settingsManager.getShowTerminalProgress()) {\n            this.ui.terminal.setProgress(false);', '        this.uninstallTerminalOutputGuard();\n        if (this.settingsManager.getShowTerminalProgress()) {\n            this.ui.terminal.setProgress(false);')
    return text


def backup(path: Path, patched_marker: str = "") -> None:
    if not path.exists():
        raise SystemExit(f"Missing expected file: {path}")
    bak = path.with_suffix(path.suffix + ".pi-local-mods.bak")
    live_is_clean = not patched_marker or patched_marker not in path.read_text()
    # Refresh the clean snapshot whenever the live file is unpatched (e.g. right
    # after `pi update` reinstalled it), so the .bak always reflects the current
    # Pi version. When the live file is already patched (a re-apply), keep the
    # existing clean snapshot instead of overwriting it with patched content.
    if live_is_clean or not bak.exists():
        shutil.copy2(path, bak)


# Markers that only appear in *patched* files, used to locate clean source.
CLEAN_MARKERS = {
    "INTERACTIVE": "class FixedBottomScrollLayout",
    "CLIPBOARD_IMAGE": "readClipboardImageViaMacOsFileUrl",
    "FOOTER": "renderMainStatusLine",
    "CUSTOM_EDITOR": "setTopBorderProvider",
    "TERMINAL": "Enable button-event mouse tracking",
    "TUI_JS": "[pi-local-mods] overlay full-redraw on appended content",
    "LEAN_CTX_INDEX": "[pi-local-mods] Bind all session-scoped work to ctx.cwd",
    "LEAN_CTX_MCP_BRIDGE": "[pi-local-mods] Pin the MCP child to the active session cwd",
}


def installed_pi_version() -> str | None:
    pkg = PI_PACKAGE / "package.json"
    if not pkg.exists():
        return None
    try:
        return json.loads(pkg.read_text()).get("version")
    except Exception:
        return None


def clean_source(path: Path, patched_marker: str) -> Path:
    """Return a path whose contents are the unpatched (clean) version of `path`.

    Prefers the live file when it is already clean; otherwise falls back to the
    `.pi-local-mods.bak` snapshot captured on first apply. Raises if neither is
    clean (e.g. Pi drifted and no clean snapshot exists).
    """
    if path.exists() and patched_marker not in path.read_text():
        return path
    bak = path.with_suffix(path.suffix + ".pi-local-mods.bak")
    if bak.exists() and patched_marker not in bak.read_text():
        return bak
    raise SystemExit(
        f"No clean source for {path} (marker {patched_marker!r} present in both "
        "live and backup). Reinstall Pi clean first: "
        "npm install -g @earendil-works/pi-coding-agent"
    )


FIXTURE_VERSION_FILE = ROOT / "tests" / "fixtures" / "VERSION"


def check_fixture_version() -> None:
    """Warn (non-fatal) if the frozen fixtures are pinned to a different Pi
    version than the one currently installed."""
    installed = installed_pi_version()
    if not installed:
        return
    if not FIXTURE_VERSION_FILE.exists():
        print(f"note: no tests/fixtures/VERSION; installed Pi is {installed}.")
        return
    pinned = FIXTURE_VERSION_FILE.read_text().strip()
    if pinned != installed:
        print(
            f"WARNING: fixtures are pinned to Pi {pinned} but installed Pi is "
            f"{installed}. Patches may have drifted — run: "
            "python3 scripts/refresh_fixtures.py"
        )


def patch_clipboard_image_attachments(text: str) -> str:
    if 'import { processImage } from "../../utils/image-process.js";' not in text:
        text = text.replace(
            'import { extensionForImageMimeType, readClipboardImage } from "../../utils/clipboard-image.js";',
            'import { extensionForImageMimeType, readClipboardImage } from "../../utils/clipboard-image.js";\nimport { processImage } from "../../utils/image-process.js";',
        )
    if 'import { detectSupportedImageMimeTypeFromFile } from "../../utils/mime.js";' not in text:
        text = text.replace(
            'import { processImage } from "../../utils/image-process.js";',
            'import { processImage } from "../../utils/image-process.js";\nimport { detectSupportedImageMimeTypeFromFile } from "../../utils/mime.js";',
        )
    if 'pendingClipboardImages = [];' not in text:
        text = text.replace(
            '    pendingUserInputs = [];\n    activeStatusIndicator = undefined;',
            '    pendingUserInputs = [];\n    pendingClipboardImages = [];\n    convertingImagePathPaste = false;\n    activeStatusIndicator = undefined;',
        )
    if 'convertingImagePathPaste = false;' not in text:
        text = text.replace(
            '    pendingClipboardImages = [];\n    activeStatusIndicator = undefined;',
            '    pendingClipboardImages = [];\n    convertingImagePathPaste = false;\n    activeStatusIndicator = undefined;',
        )
    old_run_loop = '''        // Main interactive loop
        while (true) {
            const userInput = await this.getUserInput();
            try {
                await this.session.prompt(userInput);
            }
            catch (error) {
                const errorMessage = error instanceof Error ? error.message : "Unknown error occurred";
                this.showError(errorMessage);
            }
        }
'''
    new_run_loop = '''        // Main interactive loop
        while (true) {
            const userInput = await this.getUserInput();
            const inputText = typeof userInput === "string" ? userInput : userInput.text;
            const inputOptions = typeof userInput === "string" || !userInput.images ? undefined : { images: userInput.images };
            try {
                await this.session.prompt(inputText, inputOptions);
            }
            catch (error) {
                const errorMessage = error instanceof Error ? error.message : "Unknown error occurred";
                this.showError(errorMessage);
            }
        }
'''
    if old_run_loop in text:
        text = text.replace(old_run_loop, new_run_loop, 1)
    old_paste = '''    async handleClipboardPaste() {
        try {
            const image = await readClipboardImage();
            if (image) {
                const tmpDir = os.tmpdir();
                const ext = extensionForImageMimeType(image.mimeType) ?? "png";
                const fileName = `pi-clipboard-${crypto.randomUUID()}.${ext}`;
                const filePath = path.join(tmpDir, fileName);
                fs.writeFileSync(filePath, Buffer.from(image.bytes));
                this.editor.insertTextAtCursor?.(filePath);
                this.ui.requestRender();
                return;
            }
            const text = await readClipboardText();
            if (text) {
                this.editor.insertTextAtCursor?.(text);
                this.ui.requestRender();
            }
        }
        catch {
            // Silently ignore clipboard errors (may not have permission, etc.)
        }
    }
'''
    new_paste = r'''    async handleClipboardPaste() {
        try {
            const image = await readClipboardImage();
            if (image) {
                const ext = extensionForImageMimeType(image.mimeType) ?? "png";
                const fileName = `clipboard-${crypto.randomUUID().slice(0, 8)}.${ext}`;
                const marker = `[image:${fileName}]`;
                const processed = await processImage(Buffer.from(image.bytes), image.mimeType, {
                    autoResizeImages: this.settingsManager.getImageAutoResize(),
                });
                if (processed.ok) {
                    this.pendingClipboardImages.push({
                        marker,
                        image: { type: "image", data: processed.data, mimeType: processed.mimeType },
                    });
                    this.editor.insertTextAtCursor?.(`${marker} `);
                    if (processed.hints.length > 0) {
                        this.showStatus(processed.hints.join(" "));
                    }
                    this.ui.requestRender();
                    return;
                }
                // Fallback to the old path insertion behavior if image processing fails.
                const tmpDir = os.tmpdir();
                const fallbackFileName = `pi-clipboard-${crypto.randomUUID()}.${ext}`;
                const filePath = path.join(tmpDir, fallbackFileName);
                fs.writeFileSync(filePath, Buffer.from(image.bytes));
                this.editor.insertTextAtCursor?.(filePath);
                this.showWarning(processed.message);
                this.ui.requestRender();
                return;
            }
            const text = await readClipboardText();
            if (text) {
                this.editor.insertTextAtCursor?.(text);
                this.ui.requestRender();
            }
        }
        catch {
            // Silently ignore clipboard errors (may not have permission, etc.)
        }
    }
    normalizeImagePathCandidate(candidate) {
        let value = candidate.trim();
        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
        }
        if (value.startsWith("file://")) {
            try {
                value = decodeURIComponent(new URL(value).pathname);
            }
            catch {
                value = value.slice("file://".length);
            }
        }
        value = value.replace(/\\([\\ ()'\[\]&;])/g, "$1");
        if (value.startsWith("~/")) {
            value = path.join(os.homedir(), value.slice(2));
        }
        return value;
    }
    extractImagePathMatches(text) {
        const matches = [];
        const seen = new Set();
        const patterns = [
            /file:\/\/[^\s]+\.(?:png|jpe?g|webp|gif)\b/gi,
            /"(?:[^"\\]|\\.)+\.(?:png|jpe?g|webp|gif)"/gi,
            /'(?:[^'\\]|\\.)+\.(?:png|jpe?g|webp|gif)'/gi,
            /(?:~\/|\/)(?:\\.|[^\r\n])+?\.(?:png|jpe?g|webp|gif)\b/gi,
        ];
        for (const pattern of patterns) {
            for (const match of text.matchAll(pattern)) {
                const raw = match[0];
                const filePath = this.normalizeImagePathCandidate(raw);
                const key = `${raw}\n${filePath}`;
                if (filePath && !seen.has(key)) {
                    seen.add(key);
                    matches.push({ raw, filePath });
                }
            }
        }
        return matches;
    }
    extractImagePathCandidates(text) {
        return [...new Set(this.extractImagePathMatches(text).map((match) => match.filePath))];
    }
    async attachImageFilePath(filePath, label) {
        if (!fs.existsSync(filePath)) {
            return undefined;
        }
        const mimeType = await detectSupportedImageMimeTypeFromFile(filePath);
        if (!mimeType) {
            return undefined;
        }
        const processed = await processImage(fs.readFileSync(filePath), mimeType, {
            autoResizeImages: this.settingsManager.getImageAutoResize(),
        });
        if (!processed.ok) {
            return undefined;
        }
        const safeLabel = label.replace(/[\]\n\r]/g, "_") || `dropped-${crypto.randomUUID().slice(0, 8)}`;
        const marker = `[image:${safeLabel}]`;
        this.pendingClipboardImages.push({
            marker,
            image: { type: "image", data: processed.data, mimeType: processed.mimeType },
        });
        if (processed.hints.length > 0) {
            this.showStatus(processed.hints.join(" "));
        }
        return marker;
    }
    async convertDroppedImagePaths(text) {
        if (this.convertingImagePathPaste || !text || text.includes("[image:")) {
            return;
        }
        const matches = this.extractImagePathMatches(text);
        if (matches.length === 0) {
            return;
        }
        let nextText = text;
        let converted = false;
        for (const match of matches) {
            try {
                const marker = await this.attachImageFilePath(match.filePath, path.basename(match.filePath));
                if (!marker) {
                    continue;
                }
                nextText = nextText.split(match.raw).join(marker);
                converted = true;
            }
            catch {
                // Leave the dropped path untouched if conversion fails.
            }
        }
        if (converted && nextText !== text) {
            this.convertingImagePathPaste = true;
            this.editor.setText(nextText);
            this.convertingImagePathPaste = false;
            this.ui.requestRender();
        }
    }
    async prepareClipboardImageSubmission(text) {
        const images = [];
        const remaining = [];
        for (const attachment of this.pendingClipboardImages) {
            if (text.includes(attachment.marker)) {
                images.push(attachment.image);
            }
            else {
                remaining.push(attachment);
            }
        }
        this.pendingClipboardImages = remaining;
        for (const filePath of this.extractImagePathCandidates(text)) {
            try {
                if (!fs.existsSync(filePath)) {
                    continue;
                }
                const mimeType = await detectSupportedImageMimeTypeFromFile(filePath);
                if (!mimeType) {
                    continue;
                }
                const processed = await processImage(fs.readFileSync(filePath), mimeType, {
                    autoResizeImages: this.settingsManager.getImageAutoResize(),
                });
                if (processed.ok) {
                    images.push({ type: "image", data: processed.data, mimeType: processed.mimeType });
                    if (processed.hints.length > 0) {
                        this.showStatus(processed.hints.join(" "));
                    }
                }
            }
            catch {
                // Keep the path text as a normal prompt reference if direct attachment fails.
            }
        }
        return { text, images: images.length > 0 ? images : undefined };
    }
'''
    if old_paste in text:
        text = text.replace(old_paste, new_paste, 1)
    old_prepare = '''    prepareClipboardImageSubmission(text) {
        if (this.pendingClipboardImages.length === 0) {
            return { text };
        }
        const images = [];
        const remaining = [];
        for (const attachment of this.pendingClipboardImages) {
            if (text.includes(attachment.marker)) {
                images.push(attachment.image);
            }
            else {
                remaining.push(attachment);
            }
        }
        this.pendingClipboardImages = remaining;
        return { text, images: images.length > 0 ? images : undefined };
    }
'''
    marker = '    setupEditorSubmitHandler() {'
    helper_start = new_paste.index('    normalizeImagePathCandidate(candidate) {')
    helper_text = new_paste[helper_start:]
    if '    normalizeImagePathCandidate(candidate) {' in text and marker in text:
        start = text.index('    normalizeImagePathCandidate(candidate) {')
        end = text.index(marker, start)
        text = text[:start] + helper_text + text[end:]
    elif old_prepare in text:
        text = text.replace(old_prepare, helper_text, 1)
    elif 'async prepareClipboardImageSubmission(text)' not in text and marker in text:
        text = text.replace(marker, helper_text + marker, 1)
    old_on_change = '''        this.defaultEditor.onChange = (text) => {
            const wasBashMode = this.isBashMode;
            this.isBashMode = text.trimStart().startsWith("!");
            if (wasBashMode !== this.isBashMode) {
                this.updateEditorBorderColor();
            }
        };
'''
    new_on_change = '''        this.defaultEditor.onChange = (text) => {
            const wasBashMode = this.isBashMode;
            this.isBashMode = text.trimStart().startsWith("!");
            if (wasBashMode !== this.isBashMode) {
                this.updateEditorBorderColor();
            }
            if (!this.convertingImagePathPaste) {
                void this.convertDroppedImagePaths(text);
            }
        };
'''
    if old_on_change in text:
        text = text.replace(old_on_change, new_on_change, 1)
    old_submit = '''            // Queue input during compaction (extension commands execute immediately)
            if (this.session.isCompacting) {
                if (this.isExtensionCommand(text)) {
                    this.editor.addToHistory?.(text);
                    this.editor.setText("");
                    await this.session.prompt(text);
                }
                else {
                    this.queueCompactionMessage(text, "steer");
                }
                return;
            }
            // If streaming, use prompt() with steer behavior
            // This handles extension commands (execute immediately), prompt template expansion, and queueing
            if (this.session.isStreaming) {
                this.editor.addToHistory?.(text);
                this.editor.setText("");
                await this.session.prompt(text, { streamingBehavior: "steer" });
                this.updatePendingMessagesDisplay();
                this.ui.requestRender();
                return;
            }
            // Normal message submission
            // First, move any pending bash components to chat
            this.flushPendingBashComponents();
            if (this.onInputCallback) {
                this.onInputCallback(text);
            }
            else {
                this.pendingUserInputs.push(text);
            }
            this.editor.addToHistory?.(text);
'''
    new_submit = '''            // Queue input during compaction (extension commands execute immediately)
            if (this.session.isCompacting) {
                const submission = await this.prepareClipboardImageSubmission(text);
                if (this.isExtensionCommand(text)) {
                    this.editor.addToHistory?.(text);
                    this.editor.setText("");
                    await this.session.prompt(submission.text, { images: submission.images });
                }
                else {
                    this.queueCompactionMessage(submission.text, "steer");
                    if (submission.images) {
                        this.showWarning("Image attachments cannot be preserved while compaction is running; please resend after compaction finishes.");
                    }
                }
                return;
            }
            // If streaming, use prompt() with steer behavior
            // This handles extension commands (execute immediately), prompt template expansion, and queueing
            if (this.session.isStreaming) {
                const submission = await this.prepareClipboardImageSubmission(text);
                this.editor.addToHistory?.(text);
                this.editor.setText("");
                await this.session.prompt(submission.text, { streamingBehavior: "steer", images: submission.images });
                this.updatePendingMessagesDisplay();
                this.ui.requestRender();
                return;
            }
            // Normal message submission
            const submission = await this.prepareClipboardImageSubmission(text);
            // First, move any pending bash components to chat
            this.flushPendingBashComponents();
            if (this.onInputCallback) {
                this.onInputCallback(submission);
            }
            else {
                this.pendingUserInputs.push(submission);
            }
            this.editor.addToHistory?.(text);
'''
    if old_submit in text:
        text = text.replace(old_submit, new_submit, 1)
    text = text.replace(
        'const submission = this.prepareClipboardImageSubmission(text);',
        'const submission = await this.prepareClipboardImageSubmission(text);',
    )
    required = [
        'pendingClipboardImages = [];',
        'async prepareClipboardImageSubmission(text)',
        'void this.convertDroppedImagePaths(text)',
        'this.session.prompt(inputText, inputOptions)',
        'const submission = await this.prepareClipboardImageSubmission(text);',
    ]
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"Could not apply clipboard image attachment patch: missing {missing}")
    return text


def patch_interactive() -> None:
    backup(INTERACTIVE, CLEAN_MARKERS["INTERACTIVE"])
    text = INTERACTIVE.read_text()
    text = text.replace(
        'TUI, visibleWidth, } from "@earendil-works/pi-tui";',
        'TUI, visibleWidth, sliceByColumn, truncateToWidth, } from "@earendil-works/pi-tui";',
    )
    text = text.replace(
        'TUI, visibleWidth, sliceByColumn, } from "@earendil-works/pi-tui";',
        'TUI, visibleWidth, sliceByColumn, truncateToWidth, } from "@earendil-works/pi-tui";',
    )
    if 'sliceByColumn, truncateToWidth, } from "@earendil-works/pi-tui";' not in text:
        raise SystemExit("Could not patch pi-tui import in interactive-mode.js")

    text = patch_clipboard_image_attachments(text)

    # Pi <=0.80 already had our layout class in the patched file; Pi 0.81 no
    # longer has it after upgrades. Replace it when present, otherwise insert it
    # before the first helper after InteractiveMode's top-level declarations.
    if "class FixedBottomScrollLayout {" in text:
        start = text.index("class FixedBottomScrollLayout {")
        end = text.index("\nfunction isCustomSessionEntry", start)
        text = text[:start] + FIXED_BOTTOM_SCROLL_LAYOUT + text[end:]
    else:
        marker = "function isCustomSessionEntry"
        if marker not in text:
            raise SystemExit("Could not find insertion point for FixedBottomScrollLayout")
        text = text.replace(marker, FIXED_BOTTOM_SCROLL_LAYOUT + "\n" + marker, 1)

    text = patch_terminal_log_guard(text)

    if "    fixedLayout;" not in text:
        text = text.replace(
            "    terminalLogContainer;\n    statusContainer;",
            "    terminalLogContainer;\n    statusContainer;\n    fixedLayout;",
        )
    fixed_layout_assignment = (
        "        this.fixedLayout = new FixedBottomScrollLayout(this.ui, [\n"
        "            this.headerContainer,\n"
        "            this.loadedResourcesContainer,\n"
        "            this.chatContainer,\n"
        "        ], [\n"
        "            this.pendingMessagesContainer,\n"
        "            this.terminalLogContainer,\n"
        "            this.statusContainer,\n"
        "            this.widgetContainerAbove,\n"
        "            this.editorContainer,\n"
        "            this.widgetContainerBelow,\n"
        "            this.footer,\n"
        "        ]);"
    )
    status_border_assignment = (
        "        this.footer.setMainLineVisible?.(false);\n"
        "        this.defaultEditor.setTopBorderProvider?.((width) => this.footer.renderMainStatusLine?.(width) ?? \"\");\n"
        "        this.defaultEditor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? \"\");"
    )
    text = text.replace(
        "setBottomBorderProvider?.((width) => this.footer.renderExtensionStatusLine?.(width) ?? \"\")",
        "setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? \"\")",
    )
    text = text.replace(
        "setBottomBorderProvider?.((width) => this.footer.renderExtensionStatusBorderLine?.(width) ?? \"\")",
        "setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? \"\")",
    )
    if "    bottomBorderWidgetStatus = \"\";" not in text:
        text = text.replace(
            "    widgetContainerAbove;\n    widgetContainerBelow;",
            "    widgetContainerAbove;\n    widgetContainerBelow;\n    bottomBorderWidgetStatus = \"\";\n    bottomBorderWidgetLimits = \"\";",
            1,
        )
    elif "    bottomBorderWidgetLimits = \"\";" not in text:
        text = text.replace(
            "    bottomBorderWidgetStatus = \"\";",
            "    bottomBorderWidgetStatus = \"\";\n    bottomBorderWidgetLimits = \"\";",
            1,
        )
    if "this.defaultEditor.setTopBorderProvider?.(" not in text:
        text = text.replace(
            "        this.footer.setAutoCompactEnabled(this.session.autoCompactionEnabled);",
            "        this.footer.setAutoCompactEnabled(this.session.autoCompactionEnabled);\n"
            + status_border_assignment,
            1,
        )
    elif "this.defaultEditor.setBottomBorderProvider?.(" not in text:
        text = text.replace(
            "        this.defaultEditor.setTopBorderProvider?.((width) => this.footer.renderMainStatusLine?.(width) ?? \"\");",
            "        this.defaultEditor.setTopBorderProvider?.((width) => this.footer.renderMainStatusLine?.(width) ?? \"\");\n"
            "        this.defaultEditor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? \"\");",
            1,
        )
    if "this.fixedLayout = new FixedBottomScrollLayout(" not in text:
        text = text.replace(
            status_border_assignment,
            status_border_assignment + "\n" + fixed_layout_assignment,
            1,
        )
    # A previous buggy local patch inserted the layout assignment into
    # applyRuntimeSettings() too. Keep the constructor assignment only.
    text = text.replace(
        "        this.footer.setAutoCompactEnabled(this.session.autoCompactionEnabled);\n"
        + fixed_layout_assignment
        + "\n        this.footerDataProvider.setCwd(this.sessionManager.getCwd());",
        "        this.footer.setAutoCompactEnabled(this.session.autoCompactionEnabled);\n"
        "        this.footerDataProvider.setCwd(this.sessionManager.getCwd());",
    )
    custom_editor_border_assignment = (
        '        this.editor.setTopBorderProvider?.((width) => this.footer.renderMainStatusLine?.(width) ?? "");\n'
        '        this.editor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? "");'
    )
    if "this.editor.setTopBorderProvider?.(" not in text:
        text = text.replace(
            "        this.editorContainer.addChild(this.editor);\n        this.ui.setFocus(this.editor);",
            custom_editor_border_assignment + "\n"
            "        this.editorContainer.addChild(this.editor);\n        this.ui.setFocus(this.editor);",
            1,
        )
    elif "this.editor.setBottomBorderProvider?.(" not in text:
        text = text.replace(
            '        this.editor.setTopBorderProvider?.((width) => this.footer.renderMainStatusLine?.(width) ?? "");',
            '        this.editor.setTopBorderProvider?.((width) => this.footer.renderMainStatusLine?.(width) ?? "");\n'
            '        this.editor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? "");',
            1,
        )
    old_children = '''        this.ui.addChild(this.headerContainer);
        this.ui.addChild(this.loadedResourcesContainer);
        this.ui.addChild(this.chatContainer);
        this.ui.addChild(this.pendingMessagesContainer);
        this.ui.addChild(this.statusContainer);
        this.renderWidgets(); // Initialize with default spacer
        this.ui.addChild(this.widgetContainerAbove);
        this.ui.addChild(this.editorContainer);
        this.ui.addChild(this.widgetContainerBelow);
        this.ui.addChild(this.footer);'''
    if old_children in text:
        text = text.replace(
            old_children,
            '''        this.ui.addChild(this.fixedLayout);
        this.renderWidgets(); // Initialize with default spacer''',
            1,
        )
    if "this.ui.addInputListener((data) => this.fixedLayout?.handleInput(data));" not in text:
        text = text.replace(
            "        this.setupEditorSubmitHandler();",
            "        this.setupEditorSubmitHandler();\n"
            "        this.ui.addInputListener((data) => this.fixedLayout?.handleInput(data));\n"
            "        this.ui.addInputListener((data) => this.handleCapturedTerminalLogInput(data));",
            1,
        )
    bottom_status_methods = r'''    stripStatusAnsi(text) {
        return text.replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "").replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b_[\s\S]*?(?:\x07|\x1b\\)/g, "");
    }
    compactLeanCtxStatus(text) {
        const plain = this.stripStatusAnsi(text);
        const state = plain.match(/lean-ctx\s+(\S+)/)?.[1];
        const saved = plain.match(/saved\s+([^\s]+)/)?.[1];
        const pct = plain.match(/tok\s+([^\s]+)/)?.[1];
        const cost = plain.match(/(\$[^\s]+)/)?.[1];
        const parts = [
            `${theme.fg("dim", "ctx")} ${state === "on" ? theme.fg("success", "on") : theme.fg("warning", state ?? "?")}`,
        ];
        if (saved) parts.push(theme.fg("accent", saved));
        if (pct) parts.push(theme.fg("success", pct));
        if (cost) parts.push(theme.fg("warning", cost.replace(/\.00$/, "")));
        return parts.join(theme.fg("dim", " · "));
    }
    shortLimitName(name) {
        if (/spark/i.test(name)) return "Spark";
        if (/codex/i.test(name)) return "Codex";
        if (/zai/i.test(name)) return "Zai";
        if (/gemini/i.test(name)) return "Gemini";
        return name.trim().split(/[\s/-]+/).filter(Boolean).pop() ?? name.trim();
    }
    compactLimitsStatus(text) {
        const plain = this.stripStatusAnsi(text).replace(/^\s*Limits\s*[|│]\s*/, "");
        const parts = [];
        const colorFor = (pct) => pct === undefined ? "dim" : pct >= 80 ? "success" : pct >= 50 ? "warning" : "error";
        const fmt = (pct) => theme.fg(colorFor(pct), pct === undefined ? "—" : `${pct}`);
        const compactReset = (str) => str ? str.replace(/\s+/g, "") : "—";
        const pushPart = (name, fiveHour, weekly, fiveHourReset, weeklyReset) => {
            if (!name) return;
            let part = `${theme.fg("dim", this.shortLimitName(name))} ${fmt(fiveHour)}${theme.fg("dim", "/")}${fmt(weekly)}`;
            if (fiveHourReset || weeklyReset) {
                part += ` ${theme.fg("dim", `in ${compactReset(fiveHourReset)}/${compactReset(weeklyReset)}`)}`;
            }
            parts.push(part);
        };
        for (const chunk of plain.split(/\s+[|│]\s+/)) {
            const providerChunk = chunk.replace(/\s*·\s*GPT[^:]*Spark:\s*\d+%\s+left/i, "");
            const name = providerChunk.split(/\s+(?:5h|wk):/)[0]?.trim();
            const fiveHour = providerChunk.match(/5h:\s*(\d+)%\s+left/i)?.[1];
            const weekly = providerChunk.match(/wk:\s*(\d+)%\s+left/i)?.[1];
            const fiveHourReset = providerChunk.match(/5h:\s*\d+%\s+left\s+\(in\s+([^)]+)\)/i)?.[1];
            const weeklyReset = providerChunk.match(/wk:\s*\d+%\s+left\s+\(in\s+([^)]+)\)/i)?.[1];
            pushPart(name, fiveHour ? Number(fiveHour) : undefined, weekly ? Number(weekly) : undefined, fiveHourReset, weeklyReset);
        }
        return parts.length ? `${theme.fg("dim", "lim")} ${parts.join(theme.fg("dim", " · "))}` : "";
    }
    coalesceQuotaDashboardLines(lines) {
        const statusLines = [];
        const kept = [];
        let current;
        const flush = () => {
            if (current) statusLines.push(current);
            current = undefined;
        };
        for (const line of lines) {
            const plain = this.stripStatusAnsi(line).trim();
            if (/^(?:Limits|Active)(?:\s*[|│]|$)/.test(plain)) {
                flush();
                current = plain;
            }
            else if (current) {
                current += ` ${plain}`;
            }
            else {
                kept.push(line);
            }
        }
        flush();
        return { statusLines, kept };
    }
    quotaDashboardLines(component, width) {
        return this.coalesceQuotaDashboardLines(component?.render(width) ?? []);
    }
    refreshBottomBorderWidgetStatus(width) {
        this.bottomBorderWidgetStatus = "";
        this.bottomBorderWidgetLimits = "";
        const component = this.extensionWidgetsBelow.get("quota-dashboard");
        if (!component) return;
        const { statusLines } = this.quotaDashboardLines(component, width);
        this.moveBottomWidgetStatusToEditorBorder(statusLines);
    }
    renderBottomBorderWidgetStatusLine(width) {
        if (width <= 0) {
            return "";
        }
        this.refreshBottomBorderWidgetStatus(width);
        let left = this.bottomBorderWidgetStatus || "";
        let right = this.bottomBorderWidgetLimits || "";
        if (!left && !right) {
            return "";
        }
        const minGap = left && right ? 3 : 1;
        if (left && right && visibleWidth(left) + visibleWidth(right) + minGap > width) {
            const rightLimit = Math.max(0, Math.min(visibleWidth(right), Math.floor(width * 0.45)));
            right = rightLimit > 0 ? truncateToWidth(right, rightLimit, theme.fg("dim", "…")) : "";
            const leftLimit = Math.max(0, width - visibleWidth(right) - minGap);
            left = leftLimit > 0 ? truncateToWidth(left, leftLimit, theme.fg("dim", "…")) : "";
        }
        const used = visibleWidth(left) + visibleWidth(right);
        const rail = theme.fg("borderMuted", "─".repeat(Math.max(0, width - used - (left && right ? 2 : left || right ? 1 : 0))));
        return [left, rail, right].filter(Boolean).join(" ");
    }
    moveBottomWidgetStatusToEditorBorder(lines) {
        const kept = [];
        for (const line of lines) {
            const plain = this.stripStatusAnsi(line);
            const leanCtxIndex = plain.indexOf("lean-ctx");
            if (leanCtxIndex !== -1) {
                this.bottomBorderWidgetStatus = this.compactLeanCtxStatus(plain.slice(leanCtxIndex).trim());
                continue;
            }
            const trimmedPlain = plain.trimStart();
            if (/^Limits\s*[|│]/.test(trimmedPlain)) {
                this.bottomBorderWidgetLimits = this.compactLimitsStatus(trimmedPlain);
                continue;
            }
            kept.push(line);
        }
        return kept;
    }
'''
    if "    stripStatusAnsi(text) {" in text:
        # Replace the complete injected block so repeated apply.sh runs are
        # byte-for-byte idempotent instead of accumulating duplicate methods.
        start = text.index("    stripStatusAnsi(text) {")
        end = text.index("    renderWidgets() {", start)
        text = text[:start] + bottom_status_methods + text[end:]
    else:
        text = text.replace("    renderWidgets() {", bottom_status_methods + "    renderWidgets() {", 1)
    old_render_widget_container = r'''    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {
        container.clear();
        if (widgets.size === 0) {
            if (spacerWhenEmpty) {
                container.addChild(new Spacer(1));
            }
            return;
        }
        if (leadingSpacer) {
            container.addChild(new Spacer(1));
        }
        for (const component of widgets.values()) {
            container.addChild(component);
        }
    }
'''
    previous_render_widget_container = r'''    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {
        container.clear();
        if (!leadingSpacer) {
            this.bottomBorderWidgetStatus = "";
            this.bottomBorderWidgetLimits = "";
        }
        if (widgets.size === 0) {
            if (spacerWhenEmpty) {
                container.addChild(new Spacer(1));
            }
            return;
        }
        if (leadingSpacer) {
            container.addChild(new Spacer(1));
            for (const component of widgets.values()) {
                container.addChild(component);
            }
            return;
        }
        const width = this.ui.terminal?.columns ?? 80;
        for (const component of widgets.values()) {
            const lines = this.moveBottomWidgetStatusToEditorBorder(component.render(width));
            for (const line of lines) {
                container.addChild(new Text(line, 1, 0));
            }
        }
    }
'''
    new_render_widget_container = r'''    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {
        container.clear();
        if (!leadingSpacer) {
            this.bottomBorderWidgetStatus = "";
            this.bottomBorderWidgetLimits = "";
        }
        if (widgets.size === 0) {
            if (spacerWhenEmpty) {
                container.addChild(new Spacer(1));
            }
            return;
        }
        if (leadingSpacer) {
            container.addChild(new Spacer(1));
            for (const component of widgets.values()) {
                container.addChild(component);
            }
            return;
        }
        for (const [id, component] of widgets.entries()) {
            container.addChild({
                render: (width) => {
                    if (id === "quota-dashboard") {
                        // The editor bottom-border provider owns this widget. It
                        // renders and coalesces the normal Text container once;
                        // suppress the consumed widget rows below the editor.
                        return [];
                    }
                    return this.moveBottomWidgetStatusToEditorBorder(component.render(width));
                },
                invalidate: () => component.invalidate?.(),
                dispose: () => component.dispose?.(),
            });
        }
    }
'''
    if "    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {" in text:
        text = replace_js_method(text, "    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {", new_render_widget_container.rstrip("\n"))
    # Anchor the top visible transcript line when toggling tool-output
    # expansion (ctrl+o). Without this, expanding/collapsing a tool result
    # while scrolled up in history shifts the viewport. preserveScrollAnchor
    # is defined on FixedBottomScrollLayout but had no call site here.
    set_tools_expanded_native = (
        '    setToolsExpanded(expanded) {\n'
        '        this.toolOutputExpanded = expanded;\n'
        '        const activeHeader = this.customHeader ?? this.builtInHeader;\n'
        '        if (isExpandable(activeHeader)) {\n'
        '            activeHeader.setExpanded(expanded);\n'
        '        }\n'
        '        for (const container of [this.loadedResourcesContainer, this.chatContainer]) {\n'
        '            for (const child of container.children) {\n'
        '                if (isExpandable(child)) {\n'
        '                    child.setExpanded(expanded);\n'
        '                }\n'
        '            }\n'
        '        }\n'
        '        this.ui.requestRender();\n'
        '    }'
    )
    set_tools_expanded_anchored = (
        '    setToolsExpanded(expanded) {\n'
        '        this.toolOutputExpanded = expanded;\n'
        '        const applyExpansion = () => {\n'
        '            const activeHeader = this.customHeader ?? this.builtInHeader;\n'
        '            if (isExpandable(activeHeader)) {\n'
        '                activeHeader.setExpanded(expanded);\n'
        '            }\n'
        '            for (const container of [this.loadedResourcesContainer, this.chatContainer]) {\n'
        '                for (const child of container.children) {\n'
        '                    if (isExpandable(child)) {\n'
        '                        child.setExpanded(expanded);\n'
        '                    }\n'
        '                }\n'
        '            }\n'
        '        };\n'
        '        // Keep the first visible transcript line anchored so toggling\n'
        '        // tool output (ctrl+o) does not shift the scroll position.\n'
        '        if (this.fixedLayout?.preserveScrollAnchor) {\n'
        '            this.fixedLayout.preserveScrollAnchor(applyExpansion);\n'
        '        }\n'
        '        else {\n'
        '            applyExpansion();\n'
        '            this.ui.requestRender();\n'
        '        }\n'
        '    }'
    )
    if set_tools_expanded_anchored not in text:
        if set_tools_expanded_native not in text:
            raise SystemExit("Could not find native setToolsExpanded to anchor ctrl+o scroll position")
        text = text.replace(set_tools_expanded_native, set_tools_expanded_anchored, 1)
    # Expose handleHotkeysCommand to extension shortcut handlers so a shortcut
    # (e.g. Ctrl+?) can render the keyboard-shortcuts panel directly. Without
    # this, sendUserMessage("/hotkeys") goes to the model instead of the command.
    _showhotkeys_line = "            showHotkeys: () => this.handleHotkeysCommand(),\n"
    if "showHotkeys: () => this.handleHotkeysCommand()," not in text:
        _ctx_anchor = "            getContextUsage: () => this.session.getContextUsage(),"
        if _ctx_anchor not in text:
            raise SystemExit("Could not find createContext anchor to expose showHotkeys")
        text = text.replace(_ctx_anchor, _showhotkeys_line + _ctx_anchor, 1)
    required_interactive = [
        'showHotkeys: () => this.handleHotkeysCommand(),',
        'bottomBorderWidgetStatus = "";',
        'bottomBorderWidgetLimits = "";',
        'compactLeanCtxStatus(text)',
        'compactLimitsStatus(text)',
        'refreshBottomBorderWidgetStatus(width)',
        'renderBottomBorderWidgetStatusLine(width)',
        'moveBottomWidgetStatusToEditorBorder(lines)',
        'coalesceQuotaDashboardLines(lines)',
        'quotaDashboardLines(component, width)',
        'const component = this.extensionWidgetsBelow.get("quota-dashboard");',
        'return this.coalesceQuotaDashboardLines(component?.render(width) ?? []);',
        'The editor bottom-border provider owns this widget.',
        'this.defaultEditor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? "");',
        'this.editor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? "");',
        'const applyExpansion = () => {',
        'this.fixedLayout.preserveScrollAnchor(applyExpansion);',
        'renderScrollLinesWithSpans(width)',
        'firstMeaningfulLine(childLines)',
        'grandChild instanceof UserMessageComponent',
        'findPreviousMessage(this.messageSpans, viewportTopContentLine)',
        'findNextMessage(this.messageSpans, nextThreshold)',
        'const aboveCount = start;',
        'const belowCount = this.scrollOffset;',
        'theme.fg("warning", belowTag)',
        'this.topMessageTarget = prev.start;',
        'this.bottomMessageTarget = next.start;',
        'row === this.lastBottomBarRow',
        'scrollToMessageStart(this.topMessageTarget)',
        'this.chatContainer = chatContainer ?? scrollChildren[2];',
    ]
    missing_interactive = [needle for needle in required_interactive if needle not in text]
    if missing_interactive:
        raise SystemExit(f"Could not apply bottom border widget status patch: missing {missing_interactive}")
    INTERACTIVE.write_text(text)


def patch_clipboard_image() -> None:
    backup(CLIPBOARD_IMAGE, CLEAN_MARKERS["CLIPBOARD_IMAGE"])
    text = CLIPBOARD_IMAGE.read_text()
    text = text.replace(
        'import { join } from "path";',
        'import { extname, join } from "path";',
    )
    helper = r'''function imageMimeTypeFromPath(filePath) {
    switch (extname(filePath).toLowerCase()) {
        case ".png":
            return "image/png";
        case ".jpg":
        case ".jpeg":
            return "image/jpeg";
        case ".webp":
            return "image/webp";
        case ".gif":
            return "image/gif";
        default:
            return null;
    }
}
function readClipboardImageViaMacOsFileUrl() {
    const script = [
        "try",
        "POSIX path of (the clipboard as «class furl»)",
        "on error",
        "\"\"",
        "end try",
    ];
    const result = runCommand("osascript", script.flatMap((line) => ["-e", line]), {
        timeoutMs: DEFAULT_LIST_TIMEOUT_MS,
    });
    if (!result.ok) {
        return null;
    }
    const filePath = result.stdout.toString("utf-8").trim();
    if (!filePath) {
        return null;
    }
    const mimeType = imageMimeTypeFromPath(filePath);
    if (!mimeType) {
        return null;
    }
    try {
        const bytes = readFileSync(filePath);
        if (bytes.length === 0) {
            return null;
        }
        return { bytes, mimeType };
    }
    catch {
        return null;
    }
}
'''
    if 'function readClipboardImageViaMacOsFileUrl()' not in text:
        text = text.replace('function readClipboardImageViaXclip() {', helper + 'function readClipboardImageViaXclip() {', 1)
    old = '''    else {
        image = await readClipboardImageViaNativeClipboard();
    }
'''
    new = '''    else if (platform === "darwin") {
        // Finder puts file icons/previews on the image clipboard when copying an
        // image file. Prefer the real copied file URL so the model sees the
        // actual image, not macOS' generic PNG/JPEG document preview icon.
        image = readClipboardImageViaMacOsFileUrl() ?? (await readClipboardImageViaNativeClipboard());
    }
    else {
        image = await readClipboardImageViaNativeClipboard();
    }
'''
    if old in text:
        text = text.replace(old, new, 1)
    required = ['import { extname, join } from "path";', 'function readClipboardImageViaMacOsFileUrl()', 'readClipboardImageViaMacOsFileUrl() ??']
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"Could not apply macOS clipboard file image patch: missing {missing}")
    CLIPBOARD_IMAGE.write_text(text)


FOOTER_RENDER_METHOD = r'''    setMainLineVisible(visible) {
        this.mainLineVisible = visible;
    }
    renderMainStatusLine(width) {
        if (width <= 0) {
            return "";
        }
        const state = this.session.state;
        // Calculate cumulative usage from ALL session entries (not just post-compaction messages)
        const usageTotals = createUsageTotals();
        let latestCacheHitRate;
        for (const entry of this.session.sessionManager.getEntries()) {
            if (entry.type === "message" && entry.message.role === "assistant") {
                addUsageToTotals(usageTotals, entry.message.usage);
                const latestPromptTokens = entry.message.usage.input + entry.message.usage.cacheRead + entry.message.usage.cacheWrite;
                latestCacheHitRate =
                    latestPromptTokens > 0 ? (entry.message.usage.cacheRead / latestPromptTokens) * 100 : undefined;
            }
            else if (entry.type === "message" && entry.message.role === "toolResult" && entry.message.usage) {
                addUsageToTotals(usageTotals, entry.message.usage);
            }
            else if ((entry.type === "branch_summary" || entry.type === "compaction") && entry.usage) {
                addUsageToTotals(usageTotals, entry.usage);
            }
        }
        // Calculate context usage from session (handles compaction correctly).
        // After compaction, tokens are unknown until the next LLM response.
        const contextUsage = this.session.getContextUsage();
        const contextWindow = contextUsage?.contextWindow ?? state.model?.contextWindow ?? 0;
        const contextPercentValue = contextUsage?.percent ?? 0;
        const contextPercent = contextUsage?.percent !== null ? contextPercentValue.toFixed(contextPercentValue >= 10 ? 0 : 1) : "?";
        const cwd = formatCwdForFooter(this.session.sessionManager.getCwd(), process.env.HOME || process.env.USERPROFILE);
        const branch = this.footerData.getGitBranch();
        const sessionName = this.session.sessionManager.getSessionName();
        const joinPretty = (parts) => parts.filter(Boolean).join(theme.fg("dim", " · "));
        const labelled = (label, value, valueColor = "") => `${theme.fg("dim", label)} ${valueColor ? theme.fg(valueColor, value) : value}`;
        const tokenParts = [];
        if (usageTotals.input)
            tokenParts.push(`↑${formatTokens(usageTotals.input)}`);
        if (usageTotals.output)
            tokenParts.push(`↓${formatTokens(usageTotals.output)}`);
        if (usageTotals.cacheRead)
            tokenParts.push(`R${formatTokens(usageTotals.cacheRead)}`);
        if (usageTotals.cacheWrite)
            tokenParts.push(`W${formatTokens(usageTotals.cacheWrite)}`);
        if ((usageTotals.cacheRead > 0 || usageTotals.cacheWrite > 0) && latestCacheHitRate !== undefined) {
            tokenParts.push(`CH${latestCacheHitRate.toFixed(1)}%`);
        }
        const usingSubscription = state.model
            ? state.model.provider === "kimi-coding" || this.session.modelRuntime.isUsingOAuth(state.model.provider)
            : false;
        if (usageTotals.cost || usingSubscription) {
            tokenParts.push(`$${usageTotals.cost.toFixed(3)}${usingSubscription ? " sub" : ""}`);
        }
        const autoIndicator = this.autoCompactEnabled ? " auto" : "";
        const contextPercentDisplay = contextPercent === "?"
            ? `?/${formatTokens(contextWindow)}${autoIndicator}`
            : `${contextPercent}%/${formatTokens(contextWindow)}${autoIndicator}`;
        const contextValue = contextPercentValue > 90
            ? theme.fg("error", contextPercentDisplay)
            : contextPercentValue > 70
                ? theme.fg("warning", contextPercentDisplay)
                : theme.fg("success", contextPercentDisplay);
        const modelName = state.model?.id || "no-model";
        let modelDisplay = state.model ? `${state.model.provider}/${modelName}` : modelName;
        if (state.model?.reasoning) {
            const thinkingLevel = state.thinkingLevel || "off";
            modelDisplay += thinkingLevel === "off" ? " thinking off" : ` ${thinkingLevel}`;
        }
        const buildRight = (tokenCount, includeModel) => {
            const parts = [];
            if (branch) {
                parts.push(labelled("git", branch, "warning"));
            }
            parts.push(`${theme.fg("dim", "ctx")} ${contextValue}`);
            if (tokenCount > 0) {
                parts.push(labelled("tok", tokenParts.slice(0, tokenCount).join(" ")));
            }
            if (areExperimentalFeaturesEnabled()) {
                parts.push(`${theme.fg("dim", "xp")} ${theme.bold(theme.fg("warning", "on"))}`);
            }
            if (includeModel) {
                parts.push(labelled("ai", modelDisplay, "accent"));
            }
            return joinPretty(parts);
        };
        let left = theme.fg("accent", cwd);
        if (sessionName) {
            left += `${theme.fg("dim", " • ")}${theme.fg("muted", sessionName)}`;
        }
        const minGap = 3;
        const leftWidth = visibleWidth(left);
        // Reduce by semantic units instead of clipping through a token or label:
        // the model is lowest priority, followed by token details from the end.
        const candidates = [buildRight(tokenParts.length, true), buildRight(tokenParts.length, false)];
        for (let tokenCount = tokenParts.length - 1; tokenCount >= 0; tokenCount--) {
            candidates.push(buildRight(tokenCount, false));
        }
        let right = candidates.find((candidate, index) => candidates.indexOf(candidate) === index && leftWidth + minGap + visibleWidth(candidate) <= width);
        if (right !== undefined) {
            const railWidth = Math.max(1, width - leftWidth - visibleWidth(right) - 2);
            return `${left} ${theme.fg("borderMuted", "─".repeat(railWidth))} ${right}`;
        }
        // At extreme widths even cwd + git/context cannot fit. Only then fall
        // back to ANSI-aware truncation, reserving space for both sides.
        right = buildRight(0, false);
        const rightWidth = visibleWidth(right);
        const rightLimit = Math.max(0, Math.min(rightWidth, Math.floor(width * 0.58)));
        right = rightLimit > 0 && rightWidth > rightLimit ? truncateToWidth(right, rightLimit, theme.fg("dim", "…")) : rightLimit > 0 ? right : "";
        const separatorWidth = right ? 1 : 0;
        const leftLimit = Math.max(0, width - visibleWidth(right) - separatorWidth);
        left = leftLimit > 0 ? truncateToWidth(left, leftLimit, theme.fg("dim", "…")) : "";
        const gap = Math.max(0, width - visibleWidth(left) - visibleWidth(right));
        return `${left}${" ".repeat(gap)}${right}`;
    }
    renderExtensionStatusLine(width) {
        const extensionStatuses = this.footerData.getExtensionStatuses();
        if (extensionStatuses.size === 0) {
            return "";
        }
        const sortedStatuses = Array.from(extensionStatuses.entries())
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([, text]) => sanitizeStatusText(text));
        const statusLine = `${theme.fg("dim", "dash")} ${sortedStatuses.join(theme.fg("dim", " · "))}`;
        return truncateToWidth(statusLine, width, theme.fg("dim", "…"));
    }
    renderExtensionStatusBorderLine(width) {
        const statusLine = this.renderExtensionStatusLine(width);
        if (!statusLine) {
            return "";
        }
        const statusWidth = visibleWidth(statusLine);
        if (statusWidth >= width) {
            return truncateToWidth(statusLine, width, theme.fg("dim", "…"));
        }
        return `${statusLine} ${theme.fg("borderMuted", "─".repeat(Math.max(0, width - statusWidth - 1)))}`;
    }
    renderExtensionStatusLines(width) {
        const statusLine = this.renderExtensionStatusLine(width);
        return statusLine ? [statusLine] : [];
    }
    render(width) {
        const lines = [];
        if (this.mainLineVisible !== false) {
            lines.push(this.renderMainStatusLine(width));
            lines.push(...this.renderExtensionStatusLines(width));
        }
        return lines;
    }
'''

def replace_js_method(text: str, signature: str, replacement: str) -> str:
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        char = text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[:start] + replacement + text[i + 1:]
    raise SystemExit(f"Could not find end of JS method: {signature}")

def patch_footer_component() -> None:
    backup(FOOTER, CLEAN_MARKERS["FOOTER"])
    text = FOOTER.read_text()
    if "    mainLineVisible = true;" not in text:
        text = text.replace("    autoCompactEnabled = true;", "    autoCompactEnabled = true;\n    mainLineVisible = true;", 1)
    if "    setMainLineVisible(visible) {" in text:
        start = text.index("    setMainLineVisible(visible) {")
        end = text.rindex("\n}")
        text = text[:start] + FOOTER_RENDER_METHOD + text[end:]
    else:
        text = replace_js_method(text, "    render(width) {", FOOTER_RENDER_METHOD)
    required = [
        'setMainLineVisible(visible)',
        'renderMainStatusLine(width)',
        'renderExtensionStatusLine(width)',
        'renderExtensionStatusBorderLine(width)',
        'theme.fg("borderMuted", "─".repeat(railWidth))',
        'labelled("git", branch, "warning")',
        'theme.fg("dim", "ctx")',
        'labelled("tok"',
        'labelled("ai", modelDisplay, "accent")',
        'theme.fg("dim", "dash")',
    ]
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"Could not apply footer pretty status patch: missing {missing}")
    FOOTER.write_text(text)

def patch_custom_editor() -> None:
    backup(CUSTOM_EDITOR, CLEAN_MARKERS["CUSTOM_EDITOR"])
    text = CUSTOM_EDITOR.read_text()
    if "topBorderProvider;" not in text:
        text = text.replace(
            "    onExtensionShortcut;\n",
            "    onExtensionShortcut;\n"
            "    topBorderProvider;\n"
            "    bottomBorderProvider;\n",
            1,
        )
    elif "bottomBorderProvider;" not in text:
        text = text.replace("    topBorderProvider;\n", "    topBorderProvider;\n    bottomBorderProvider;\n", 1)
    custom_methods = r'''    setTopBorderProvider(provider) {
        this.topBorderProvider = provider;
        this.tui.requestRender();
    }
    setBottomBorderProvider(provider) {
        this.bottomBorderProvider = provider;
        this.tui.requestRender();
    }
    frameLine(line, width, left, right) {
        if (width <= 1) {
            return this.borderColor(left);
        }
        const sidePadding = width >= 4 ? 1 : 0;
        const innerWidth = Math.max(0, width - 2 - sidePadding * 2);
        const borderColoredLine = line.replace(/─/g, this.borderColor("─"));
        const fitted = visibleWidth(borderColoredLine) > innerWidth
            ? truncateToWidth(borderColoredLine, innerWidth, "")
            : `${borderColoredLine}${" ".repeat(Math.max(0, innerWidth - visibleWidth(borderColoredLine)))}`;
        const pad = " ".repeat(sidePadding);
        return `${this.borderColor(left)}${pad}${fitted}${pad}${this.borderColor(right)}`;
    }
    render(width) {
        const lines = super.render(width);
        if (lines.length === 0) {
            return lines;
        }
        const sidePadding = width >= 4 ? 1 : 0;
        const contentWidth = Math.max(0, width - 2 - sidePadding * 2);
        if (this.topBorderProvider && this.scrollOffset === 0) {
            const line = this.topBorderProvider(contentWidth);
            if (line) {
                lines[0] = line;
            }
        }
        const terminalRows = this.tui.terminal.rows;
        const maxVisibleLines = Math.max(5, Math.floor(terminalRows * 0.3));
        const layoutLines = this.layoutText(this.lastWidth);
        const visibleLineCount = layoutLines.slice(this.scrollOffset, this.scrollOffset + maxVisibleLines).length;
        const bottomBorderIndex = Math.min(lines.length - 1, 1 + visibleLineCount);
        if (this.bottomBorderProvider && bottomBorderIndex >= 0 && bottomBorderIndex < lines.length) {
            const line = this.bottomBorderProvider(contentWidth, lines[bottomBorderIndex]);
            if (line) {
                lines[bottomBorderIndex] = line;
            }
        }
        const framed = [];
        for (let i = 0; i <= bottomBorderIndex; i++) {
            if (i === 0) framed.push(this.frameLine(lines[i] ?? "", width, "╭", "╮"));
            else if (i === bottomBorderIndex) framed.push(this.frameLine(lines[i] ?? "", width, "╰", "╯"));
            else framed.push(this.frameLine(lines[i] ?? "", width, "│", "│"));
        }
        return [...framed, ...lines.slice(bottomBorderIndex + 1)];
    }
'''
    if "    setTopBorderProvider(provider) {" in text and "    onAction(action, handler) {" in text:
        start = text.index("    setTopBorderProvider(provider) {")
        end = text.index("    onAction(action, handler) {", start)
        text = text[:start] + custom_methods + text[end:]
    elif "    onAction(action, handler) {" in text:
        text = text.replace("    onAction(action, handler) {", custom_methods + "    onAction(action, handler) {", 1)
    if 'import { Editor } from "@earendil-works/pi-tui";' in text:
        text = text.replace(
            'import { Editor } from "@earendil-works/pi-tui";',
            'import { Editor, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";',
            1,
        )
    required = ["topBorderProvider;", "bottomBorderProvider;", "setTopBorderProvider(provider)", "setBottomBorderProvider(provider)", "frameLine(line, width, left, right)", "const lines = super.render(width)", "this.scrollOffset === 0", "bottomBorderIndex", "truncateToWidth"]
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"Could not apply custom editor border patch: missing {missing}")
    CUSTOM_EDITOR.write_text(text)

def patch_terminal() -> None:
    backup(TERMINAL, CLEAN_MARKERS["TERMINAL"])
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


def patch_tui_overlay_scroll() -> None:
    """Force a clean full repaint when a visible overlay participates in a changed frame.

    pi-tui's differential writer only repaints changed lines in the composited
    frame. Screen-fixed overlays (e.g. the pi-subagents fleet inspector) can be
    corrupted both when chat content behind them appends and when the overlay
    panel itself changes. In either case, repainting only the changed slice can
    leave stale overlay rows/cells behind because the terminal state is not the
    same as the composited in-memory frame. Re-deriving the whole frame from the
    in-memory buffer also rebuilds scrollback, so no chat history is lost.
    """
    marker = CLEAN_MARKERS["TUI_JS"]
    backup(TUI_JS, marker)
    text = clean_source(TUI_JS, marker).read_text()
    needle = "        const appendStart = appendedLines && firstChanged === this.previousLines.length && firstChanged > 0;\n"
    guard = (
        needle
        + "        // " + marker + "\n"
        + "        // Overlays are screen-fixed; any changed composited overlay frame\n"
        + "        // can leave stale rows/cells behind under the differential writer.\n"
        + "        if (firstChanged !== -1 && this.overlayStack.some((entry) => this.isOverlayVisible(entry))) {\n"
        + "            logRedraw(\"overlay active + changed frame\");\n"
        + "            fullRender(true);\n"
        + "            return;\n"
        + "        }\n"
    )
    if needle not in text:
        raise SystemExit("Could not anchor TUI overlay-scroll patch (appendStart line not found)")
    text = text.replace(needle, guard, 1)
    TUI_JS.write_text(text)


def patch_lean_ctx_session_cwd() -> None:
    """Bind pi-lean-ctx subprocesses to Pi's active session cwd.

    Pi can resume a session whose persisted cwd differs from process.cwd(). The
    upstream extension starts its MCP child during factory loading and lets the
    child inherit process.cwd(), which can be Pi's installed package directory.
    Starting from session_start and passing ctx.cwd to the MCP transport keeps
    the lean-ctx path jail aligned with the active session. The same rule is
    applied to wrapped Pi tools and one-shot lean-ctx commands.
    """
    if not LEAN_CTX_PACKAGE.exists():
        return

    backup(LEAN_CTX_INDEX, CLEAN_MARKERS["LEAN_CTX_INDEX"])
    backup(LEAN_CTX_MCP_BRIDGE, CLEAN_MARKERS["LEAN_CTX_MCP_BRIDGE"])
    # Always regenerate from clean sources. This makes re-applying a revised
    # local patch deterministic instead of layering edits over an older patch.
    index = clean_source(LEAN_CTX_INDEX, CLEAN_MARKERS["LEAN_CTX_INDEX"]).read_text()
    bridge = clean_source(LEAN_CTX_MCP_BRIDGE, CLEAN_MARKERS["LEAN_CTX_MCP_BRIDGE"]).read_text()

    def replace_required(text: str, old: str, new: str, label: str | None = None, expected: int = 1) -> str:
        count = text.count(old)
        if count != expected:
            anchor = label or old.splitlines()[0][:80]
            raise SystemExit(
                f"Could not apply pi-lean-ctx session cwd patch ({anchor}): "
                f"expected {expected} exact match(es), found {count}"
            )
        return text.replace(old, new)

    index = replace_required(index,
        '''function isMcpAdapterConfigured(): boolean {
  const home = homedir();
  const mcpConfigPaths = [
    resolve(home, ".pi", "agent", "mcp.json"),
    resolve(process.cwd(), ".pi", "mcp.json"),
  ];''',
        '''function isMcpAdapterConfigured(projectCwd = process.cwd()): boolean {
  const home = homedir();
  const mcpConfigPaths = [
    resolve(home, ".pi", "agent", "mcp.json"),
    resolve(projectCwd, ".pi", "mcp.json"),
  ];''',
    )
    index = replace_required(index,
        '''async function execLeanCtx(pi: ExtensionAPI, args: string[]) {
  const bin = resolveBinary();
  const result = await pi.exec(bin, args);''',
        '''async function execLeanCtx(pi: ExtensionAPI, args: string[], cwd?: string) {
  const bin = resolveBinary();
  const result = await pi.exec(bin, args, cwd ? { cwd } : undefined);''',
    )
    index = replace_required(index,
        '''  const baseBashTool = createBashToolDefinition(process.cwd(), {
    spawnHook: ({ command, cwd, env }) => {
      const bin = resolveBinary();
      return {
        command: `${shellQuote(bin)} -c ${shellQuote(command)}`,
        cwd,
        env: leanCtxEnv(env),
      };
    },
  });

  const rawBash = createBashToolDefinition(process.cwd());''',
        '''  const createCompressedBashTool = (cwd: string) => createBashToolDefinition(cwd, {
    spawnHook: ({ command, cwd, env }) => {
      const bin = resolveBinary();
      return {
        command: `${shellQuote(bin)} -c ${shellQuote(command)}`,
        cwd,
        env: leanCtxEnv(env),
      };
    },
  });

  // Rendering does not execute the definition; execution below creates a
  // cwd-bound definition from ctx.cwd for every call.
  const bashRendererTool = createCompressedBashTool(".");''',
    )
    index = replace_required(index,"return baseBashTool.renderResult", "return bashRendererTool.renderResult")
    index = replace_required(index,"? baseBashTool.renderResult(", "? bashRendererTool.renderResult(")
    index = replace_required(index,
        "      const tool = isRaw ? rawBash : baseBashTool;",
        "      const tool = isRaw ? createBashToolDefinition(ctx.cwd) : createCompressedBashTool(ctx.cwd);",
    )
    index = replace_required(index,
        "  const nativeReadTool = createReadToolDefinition(process.cwd());",
        "  const nativeReadTool = createReadToolDefinition(\".\");",
    )
    index = replace_required(index,
        "        return nativeReadTool.execute(_toolCallId, { ...params, path: absolutePath }, signal, onUpdate, ctx);",
        "        return createReadToolDefinition(ctx.cwd).execute(_toolCallId, { ...params, path: absolutePath }, signal, onUpdate, ctx);",
    )
    index = replace_required(
        index,
        "await execLeanCtx(pi, args);",
        "await execLeanCtx(pi, args, ctx.cwd);",
        "ctx_read CLI fallbacks",
        expected=2,
    )
    index = replace_required(index,
        'await execLeanCtx(pi, ["ls", absolutePath]);',
        'await execLeanCtx(pi, ["ls", absolutePath], ctx.cwd);',
    )
    index = replace_required(index,
        'await execLeanCtx(pi, ["find", params.pattern, absolutePath]);',
        'await execLeanCtx(pi, ["find", params.pattern, absolutePath], ctx.cwd);',
    )
    index = replace_required(index,
        'const result = await pi.exec(bin, ["-c", ...searchArgs]);',
        'const result = await pi.exec(bin, ["-c", ...searchArgs], { cwd: ctx.cwd });',
    )
    index = replace_required(index,
        '''    async execute(_toolCallId, params) {
      const output = await execLeanCtx(pi, params.args);''',
        '''    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      const output = await execLeanCtx(pi, params.args, ctx.cwd);''',
    )
    index = replace_required(index,
        "  const nativeLsTool = createLsToolDefinition(process.cwd());\n  const nativeFindTool = createFindToolDefinition(process.cwd());\n  const nativeGrepTool = createGrepToolDefinition(process.cwd());",
        "  const nativeLsTool = createLsToolDefinition(\".\");\n  const nativeFindTool = createFindToolDefinition(\".\");\n  const nativeGrepTool = createGrepToolDefinition(\".\");",
    )
    index = replace_required(index,
        '''  const adapterConfigured = isMcpAdapterConfigured();
  // An explicit opt-in to the embedded bridge wins over mcp.json detection (#361).
  // A `lean-ctx` entry in ~/.pi/agent/mcp.json does NOT prove that pi-mcp-adapter
  // is actually serving it — pi has no native MCP support, and `lean-ctx init
  // --agent pi` writes that entry by default — so it must not silently disable the
  // bridge a user explicitly requested via LEAN_CTX_PI_ENABLE_MCP=1 / enableMcp.
  mcpBridge = enableMcpBridge
    ? new McpBridge(resolveBinary(), PI_CONFIG.forwardedEnv, {
        disabledTools: PI_CONFIG.disabledTools,
        toolPrefix: PI_CONFIG.toolPrefix,
        localTools: localToolNames,
      })
    : null;

  if (mcpBridge) {
    pi.on("session_shutdown", async () => {
      await mcpBridge?.shutdown();
    });''',
        '''  let adapterConfigured = isMcpAdapterConfigured();
  // An explicit opt-in to the embedded bridge wins over mcp.json detection (#361).
  // A `lean-ctx` entry in ~/.pi/agent/mcp.json does NOT prove that pi-mcp-adapter
  // is actually serving it — pi has no native MCP support, and `lean-ctx init
  // --agent pi` writes that entry by default — so it must not silently disable the
  // bridge a user explicitly requested via LEAN_CTX_PI_ENABLE_MCP=1 / enableMcp.
  if (enableMcpBridge) {
    // [pi-local-mods] Bind all session-scoped work to ctx.cwd. Pi may resume a
    // session from a different directory than process.cwd(), so starting the
    // long-lived child during factory loading gives lean-ctx the wrong path jail.
    pi.on("session_start", async (_event, ctx) => {
      // A runner normally emits session_start once. Keep this idempotent so an
      // accidental duplicate cannot replace the bridge captured by MCP tools.
      if (mcpBridge) return;
      adapterConfigured = isMcpAdapterConfigured(ctx.cwd);
      mcpBridge = new McpBridge(resolveBinary(), PI_CONFIG.forwardedEnv, {
        cwd: ctx.cwd,
        disabledTools: PI_CONFIG.disabledTools,
        toolPrefix: PI_CONFIG.toolPrefix,
        localTools: localToolNames,
      });
      await mcpBridge.start(pi);
    });

    pi.on("session_shutdown", async () => {
      const bridge = mcpBridge;
      mcpBridge = null;
      await bridge?.shutdown();
    });''',
    )
    index = replace_required(index,
        '''
    try {
      await mcpBridge.start(pi);
    } catch (err) {
      console.error(`[pi-lean-ctx] MCP bridge startup failed: ${err}`);
    }
  }
''',
        '''
  }
''',
        "remove factory-time MCP startup",
    )
    index = replace_required(
        index,
        '''  // Declared up-front so the ctx_read handler (registered below) can route
  // through the embedded bridge once it connects. Assigned after the tools are
  // registered (the bridge is started at the end of this function).''',
        '''  // Declared up-front so the ctx_read handler (registered below) can route
  // through the embedded bridge once session_start connects it.''',
        "update bridge lifecycle comment",
    )

    required_index = [
        "[pi-local-mods] Bind all session-scoped work to ctx.cwd",
        "function isMcpAdapterConfigured(projectCwd = process.cwd())",
        "pi.exec(bin, args, cwd ? { cwd } : undefined)",
        "createCompressedBashTool(ctx.cwd)",
        "createReadToolDefinition(ctx.cwd).execute",
        "new McpBridge(resolveBinary(), PI_CONFIG.forwardedEnv, {\n        cwd: ctx.cwd,",
    ]
    missing_index = [marker for marker in required_index if marker not in index]
    forbidden_index = [
        "mcpBridge = enableMcpBridge\n    ? new McpBridge",
        "const rawBash = createBashToolDefinition(process.cwd())",
        "const baseBashTool = createBashToolDefinition(process.cwd()",
        "const nativeReadTool = createReadToolDefinition(process.cwd())",
        "const nativeLsTool = createLsToolDefinition(process.cwd())",
    ]
    remaining_index = [marker for marker in forbidden_index if marker in index]
    if missing_index or remaining_index:
        raise SystemExit(
            "Could not apply pi-lean-ctx session cwd patch to index.ts: "
            f"missing={missing_index}, remaining={remaining_index}"
        )
    bridge = replace_required(bridge,
        '''  /** Optional prefix applied to the Pi-facing tool name (not the MCP call). */
  toolPrefix?: string;''',
        '''  /** Active Pi session cwd used as the MCP server root and path jail. */
  cwd?: string;
  /** Optional prefix applied to the Pi-facing tool name (not the MCP call). */
  toolPrefix?: string;''',
    )
    bridge = replace_required(bridge,
        '''  private binary: string;
  private extraEnv: Record<string, string>;''',
        '''  private binary: string;
  private cwd: string;
  private extraEnv: Record<string, string>;''',
    )
    bridge = replace_required(bridge,
        '''    this.binary = binary;
    this.extraEnv = extraEnv;''',
        '''    this.binary = binary;
    this.cwd = policy.cwd ?? process.cwd();
    this.extraEnv = extraEnv;''',
    )
    bridge = replace_required(
        bridge,
        '''  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private shuttingDown = false;''',
        '''  private reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  private reconnectPromise: Promise<void> | undefined;
  private shuttingDown = false;''',
        "add single-flight reconnect state",
    )
    bridge = replace_required(bridge,
        '''      env: { ...this.extraEnv, ...process.env, LEAN_CTX_COMPRESS: "1" },
      stderr: "pipe",''',
        '''      env: { ...this.extraEnv, ...process.env, LEAN_CTX_COMPRESS: "1" },
      // [pi-local-mods] Pin the MCP child to the active session cwd so the
      // server's project root and path jail match Pi's ctx.cwd.
      cwd: this.cwd,
      stderr: "pipe",''',
    )
    bridge = replace_required(
        bridge,
        '''  private async forceReconnect(): Promise<void> {
    if (this.shuttingDown) return;
    this.connected = false;
    try {
      await this.client?.close();
    } catch {
      // best-effort cleanup
    }
    this.client = null;
    this.transport = null;
    await this.connect();
  }''',
        '''  private async forceReconnect(): Promise<void> {
    if (this.shuttingDown) return;
    if (this.reconnectPromise) return this.reconnectPromise;

    const reconnect = (async () => {
      this.connected = false;
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = undefined;
      }

      // [pi-local-mods] An intentional close must not also schedule the normal
      // delayed reconnect. Detach the old transport before closing it, otherwise
      // its onclose callback can race the immediate reconnect and leak a child.
      const client = this.client;
      const transport = this.transport;
      this.client = null;
      this.transport = null;
      if (transport) transport.onclose = undefined;
      try {
        await client?.close();
      } catch {
        // best-effort cleanup
      }
      await this.connect();
    })();

    this.reconnectPromise = reconnect;
    try {
      await reconnect;
    } finally {
      if (this.reconnectPromise === reconnect) this.reconnectPromise = undefined;
    }
  }''',
        "suppress delayed reconnect during intentional close",
    )
    required_bridge = [
        "[pi-local-mods] Pin the MCP child to the active session cwd",
        "  cwd?: string;",
        "    this.cwd = policy.cwd ?? process.cwd();",
        "      cwd: this.cwd,",
        "[pi-local-mods] An intentional close must not also schedule",
        "if (transport) transport.onclose = undefined;",
        "if (this.reconnectPromise) return this.reconnectPromise;",
        "this.reconnectPromise = reconnect;",
    ]
    missing_bridge = [marker for marker in required_bridge if marker not in bridge]
    if missing_bridge:
        raise SystemExit(
            "Could not apply pi-lean-ctx session cwd patch to mcp-bridge.ts: "
            f"missing={missing_bridge}"
        )
    # Stage and syntax-check both outputs before replacing either live file.
    # The constructor call remains backward-compatible across the two versions,
    # and rollback restores both originals if either replace fails.
    # Install the backward-compatible bridge first. A hard process crash between
    # replacements therefore leaves old index + new bridge (old behavior), never
    # new index + old bridge (which would ignore the supplied session cwd).
    staged = [
        (LEAN_CTX_MCP_BRIDGE, bridge),
        (LEAN_CTX_INDEX, index),
    ]
    originals = {path: path.read_text() for path, _text in staged}
    temp_paths: list[Path] = []
    try:
        for path, text in staged:
            fd, temp_name = tempfile.mkstemp(
                dir=path.parent,
                prefix=f".{path.stem}.pi-local-mods.",
                suffix=path.suffix,
            )
            os.close(fd)
            temp = Path(temp_name)
            temp_paths.append(temp)
            temp.write_text(text)
            shutil.copymode(path, temp)
            subprocess.run(["node", "--check", str(temp)], check=True)
        for (path, _text), temp in zip(staged, temp_paths):
            os.replace(temp, path)
    except BaseException:
        for path, original in originals.items():
            path.write_text(original)
        raise
    finally:
        for temp in temp_paths:
            temp.unlink(missing_ok=True)


def patch_bg_tasks_shortcuts() -> None:
    if not BG_TASKS_PACKAGE.exists():
        return

    backup(BG_TASKS_SHORTCUTS)
    shortcuts = BG_TASKS_SHORTCUTS.read_text()
    shortcuts = shortcuts.replace(
        " *   - Ctrl+B (and Ctrl+Shift+B alias): move the foreground bash to background\n",
        " *   - Ctrl+Shift+B: move the foreground bash to background\n",
    )
    shortcuts = shortcuts.replace(
        '''    // Primary background shortcut — Ctrl+B, matching Claude Code. Inside a tmux\n    // session Ctrl+B is tmux's prefix key and must be pressed twice; the live\n    // hint shown while a command runs says so.\n    pi.registerShortcut("ctrl+b", {\n        description: "Background the current foreground process",\n        handler: async (ctx) => handleCtrlB(reg, pi, ctx),\n    });\n\n    // Alias for muscle memory / terminals that remap Ctrl+B.\n    pi.registerShortcut("ctrl+shift+b", {\n        description: "Background the current foreground process (alias for Ctrl+B)",\n        handler: async (ctx) => handleCtrlB(reg, pi, ctx),\n    });\n''',
        '''    // Primary background shortcut. Ctrl+B is reserved by Pi's built-in editor\n    // cursor-left binding, so use Ctrl+Shift+B to avoid shortcut conflicts.\n    pi.registerShortcut("ctrl+shift+b", {\n        description: "Background the current foreground process",\n        handler: async (ctx) => handleCtrlB(reg, pi, ctx),\n    });\n''',
    )
    shortcuts = shortcuts.replace(
        " * Ctrl+B / Ctrl+Shift+B handler — hand control back to the agent (Claude Code\n",
        " * Ctrl+Shift+B handler — hand control back to the agent (Claude Code\n",
    )
    if 'pi.registerShortcut("ctrl+b"' in shortcuts:
        raise SystemExit("Could not remove pi-patty-bg-tasks ctrl+b shortcut registration")
    if 'pi.registerShortcut("ctrl+shift+b"' not in shortcuts:
        raise SystemExit("Could not verify pi-patty-bg-tasks ctrl+shift+b shortcut registration")
    BG_TASKS_SHORTCUTS.write_text(shortcuts)

    backup(BG_TASKS_HINT)
    hint = BG_TASKS_HINT.read_text()
    hint = hint.replace(
        ' * Live "(ctrl+b to run in background)" hint shown below the editor while a\n',
        ' * Live "(ctrl+shift+b to run in background)" hint shown below the editor while a\n',
    )
    hint = hint.replace(
        ''' * The key to press to background, as shown in the hint. Inside a tmux session\n * `ctrl+b` is tmux's prefix key, so it must be pressed twice — Claude Code\n * shows the same "(twice)" note.\n */\nfunction backgroundHintLabel(): string {\n    return process.env.TMUX\n        ? "ctrl+b ctrl+b (twice) to run in background"\n        : "ctrl+b to run in background";\n}\n''',
        ''' * The key to press to background, as shown in the hint.\n */\nfunction backgroundHintLabel(): string {\n    return "ctrl+shift+b to run in background";\n}\n''',
    )
    if 'ctrl+b to run in background' in hint or 'ctrl+b ctrl+b' in hint:
        raise SystemExit("Could not update pi-patty-bg-tasks background hint")
    BG_TASKS_HINT.write_text(hint)


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


def install_quota_dashboard() -> None:
    if not QUOTA_DASHBOARD_SRC.exists():
        raise SystemExit(f"quota-dashboard source missing: {QUOTA_DASHBOARD_SRC}")
    QUOTA_DASHBOARD_DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(QUOTA_DASHBOARD_SRC, QUOTA_DASHBOARD_DST)


def verify() -> None:
    paths = [INTERACTIVE, CLIPBOARD_IMAGE, FOOTER, CUSTOM_EDITOR, TERMINAL, TUI_JS]
    if LEAN_CTX_PACKAGE.exists():
        paths.extend([LEAN_CTX_INDEX, LEAN_CTX_MCP_BRIDGE])
    for path in paths:
        subprocess.run(["node", "--check", str(path)], check=True)


def main() -> None:
    check_fixture_version()
    patch_interactive()
    patch_clipboard_image()
    patch_footer_component()
    patch_custom_editor()
    patch_terminal()
    patch_tui_overlay_scroll()
    patch_lean_ctx_session_cwd()
    patch_bg_tasks_shortcuts()
    install_theme()
    install_quota_dashboard()
    verify()
    print("Applied pi-local-mods. Restart pi to use the patched runtime.")


if __name__ == "__main__":
    main()
