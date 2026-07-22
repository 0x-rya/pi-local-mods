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
    text = patch_terminal_log_guard(text)
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
