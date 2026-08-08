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
TUI_UTILS = PI_PACKAGE / "node_modules/@earendil-works/pi-tui/dist/utils.js"
BG_TASKS_PACKAGE = PI_AGENT_DIR / "npm/node_modules/pi-patty-bg-tasks"
BG_TASKS_SHORTCUTS = BG_TASKS_PACKAGE / "src/shortcuts.ts"
BG_TASKS_HINT = BG_TASKS_PACKAGE / "src/hint.ts"
LEAN_CTX_PACKAGE = PI_AGENT_DIR / "npm/node_modules/pi-lean-ctx"
LEAN_CTX_INDEX = LEAN_CTX_PACKAGE / "extensions/index.ts"
LEAN_CTX_MCP_BRIDGE = LEAN_CTX_PACKAGE / "extensions/mcp-bridge.ts"
EXTENSION_SOURCES = (
    ROOT / "extensions" / "quota-dashboard.ts",
    ROOT / "extensions" / "terminal-logs.ts",
)

PROMPT_NAVIGATION_METHODS = r'''    getPromptNavigationState(width, refresh = false) {
        const scrollView = this.transcriptScrollView;
        if (!scrollView || width <= 0 || scrollView.viewportHeight <= 0) {
            return { previous: undefined, next: undefined };
        }
        const cached = this.promptNavigationStateCache;
        if (!refresh && cached && cached.width === width && cached.scrollTop === scrollView.scrollTop && cached.viewportHeight === scrollView.viewportHeight) {
            return cached.state;
        }
        const contentWidth = scrollView.getContentWidth(width);
        let line = this.headerContainer.render(contentWidth).length + this.loadedResourcesContainer.render(contentWidth).length;
        const spans = [];
        for (const child of this.chatContainer.children) {
            const childLines = child.render(contentWidth);
            const start = line;
            const end = start + childLines.length - 1;
            if (child instanceof UserMessageComponent) {
                let preview = "";
                for (const raw of childLines) {
                    const plain = raw
                        .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
                        .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
                        .replace(/\x1b_[\s\S]*?(?:\x07|\x1b\\)/g, "")
                        .trim();
                    if (plain && /\p{L}|\p{N}/u.test(plain)) {
                        preview = plain;
                        break;
                    }
                }
                if (preview) {
                    spans.push({ start, end, preview });
                }
            }
            line += childLines.length;
        }
        const viewportStart = scrollView.scrollTop;
        const viewportEnd = viewportStart + scrollView.viewportHeight;
        let previous;
        let next;
        for (const span of spans) {
            if (span.start < viewportStart) {
                previous = span;
            }
            else if (!next && span.start >= viewportEnd) {
                next = span;
            }
        }
        const state = { previous, next };
        this.promptNavigationStateCache = {
            width,
            scrollTop: scrollView.scrollTop,
            viewportHeight: scrollView.viewportHeight,
            state,
        };
        return state;
    }
    renderPromptNavigationBar(direction, width, refresh = false) {
        const state = this.getPromptNavigationState(width, refresh);
        const target = direction < 0 ? state.previous : state.next;
        if (!target || width <= 0) {
            return [];
        }
        const scrollView = this.transcriptScrollView;
        const edge = direction < 0 ? scrollView.scrollTop : scrollView.scrollTop + scrollView.viewportHeight;
        const distance = Math.max(1, Math.abs(target.start - edge));
        const arrow = direction < 0 ? "↑" : "↓";
        const lead = `${distance}${arrow}`;
        const suffix = " · click to jump";
        const previewWidth = Math.max(0, width - visibleWidth(lead) - visibleWidth(suffix) - 1);
        const preview = truncateToWidth(target.preview, previewWidth, theme.fg("dim", "…"));
        let line = theme.fg("accent", lead) + " " + theme.fg("muted", preview) + theme.fg("dim", suffix);
        if (visibleWidth(line) > width) {
            line = truncateToWidth(line, width, theme.fg("dim", "…"));
        }
        const destination = direction < 0 ? "previous" : "next";
        return [hyperlink(line, `pi://prompt-navigation/${destination}`)];
    }
    navigatePromptBar(direction) {
        const width = this.ui.terminal?.columns ?? 80;
        const state = this.getPromptNavigationState(width, true);
        const target = direction < 0 ? state.previous : state.next;
        if (!target) {
            return;
        }
        this.transcriptScrollView.scrollTo(target.start);
        this.ui.requestRender();
    }
    handleInteractiveUrl(url) {
        if (url === "pi://prompt-navigation/previous") {
            this.navigatePromptBar(-1);
            return;
        }
        if (url === "pi://prompt-navigation/next") {
            this.navigatePromptBar(1);
            return;
        }
        if (url.startsWith("pi-local://")) {
            const registry = globalThis[Symbol.for("pi-local-mods.action-handlers")];
            if (registry instanceof Map) {
                for (const [prefix, handler] of registry) {
                    if (url.startsWith(prefix) && typeof handler === "function") {
                        try {
                            if (handler(url) !== false) {
                                return;
                            }
                        }
                        catch (error) {
                            this.showWarning(`Local action failed: ${error instanceof Error ? error.message : String(error)}`);
                            return;
                        }
                    }
                }
            }
            this.showWarning(`No local action handler is registered for ${url}`);
            return;
        }
        openBrowser(url);
    }
'''

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
    "INTERACTIVE": "pendingClipboardImages = [];",
    "CLIPBOARD_IMAGE": "readClipboardImageViaMacOsFileUrl",
    "FOOTER": "renderMainStatusLine",
    "CUSTOM_EDITOR": "setTopBorderProvider",
    "TUI_UTILS": "[pi-local-mods] Match Ghostty's cell advance",
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
        // Dragged macOS paths are shell-escaped, including Unicode whitespace
        // such as the narrow no-break space before AM/PM in screenshot names.
        // Unescape any backslash-escaped non-newline character so existsSync()
        // sees the real filesystem path.
        value = value.replace(/\\([^\r\n])/g, "$1");
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
        if (this.convertingImagePathPaste || !text) {
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
    text = clean_source(INTERACTIVE, CLEAN_MARKERS["INTERACTIVE"]).read_text()
    import_suffix = '} from "@earendil-works/pi-tui";'
    import_lines = [
        line for line in text.splitlines()
        if line.startswith("import {") and import_suffix in line
    ]
    if len(import_lines) != 1:
        raise SystemExit(
            "Could not find the named pi-tui import in interactive-mode.js"
        )
    import_line = import_lines[0]
    for name in ("truncateToWidth",):
        if name not in import_line:
            import_line = import_line.replace(import_suffix, f"{name}, {import_suffix}")
    text = text.replace(import_lines[0], import_line, 1)

    if "openUrl: options.openUrl ?? openBrowser," not in text:
        text = text.replace(
            "            openUrl: openBrowser,",
            "            openUrl: options.openUrl ?? openBrowser,",
            1,
        )
    prompt_url_callback = "            openUrl: (url) => this.handleInteractiveUrl(url),\n"
    if prompt_url_callback not in text:
        callback_anchor = "            onRightClickPaste: this.onRightClickPaste,\n"
        if text.count(callback_anchor) != 2:
            raise SystemExit("Could not anchor fullscreen prompt-navigation URL callbacks")
        text = text.replace(callback_anchor, callback_anchor + prompt_url_callback)
    if "    promptNavigationTopBar =" not in text:
        text = text.replace(
            "    transcriptScrollView;\n    fullscreenLayoutRoot;",
            "    transcriptScrollView;\n"
            "    promptNavigationStateCache = undefined;\n"
            "    promptNavigationTopBar = {\n"
            "        render: (width) => this.renderPromptNavigationBar(-1, width, true),\n"
            "        invalidate: () => { this.promptNavigationStateCache = undefined; },\n"
            "    };\n"
            "    promptNavigationBottomBar = {\n"
            "        render: (width) => this.renderPromptNavigationBar(1, width),\n"
            "        invalidate: () => { this.promptNavigationStateCache = undefined; },\n"
            "    };\n"
            "    fullscreenLayoutRoot;",
            1,
        )
    if "    getPromptNavigationState(" in text:
        start = text.index("    getPromptNavigationState(")
        end = text.index("    mountInteractiveTui(tui, components) {", start)
        text = text[:start] + PROMPT_NAVIGATION_METHODS + text[end:]
    else:
        text = text.replace(
            "    mountInteractiveTui(tui, components) {",
            PROMPT_NAVIGATION_METHODS + "    mountInteractiveTui(tui, components) {",
            1,
        )
    native_fullscreen_layout = '''        this.fullscreenLayoutRoot = new TuiLayouts.VStack([
            { component: this.transcriptScrollView, basis: 0, grow: 1, shrink: 1, minSize: 1 },
            { component: dock, basis: "auto", grow: 0, shrink: 1, minSize: 1 },
        ]);'''
    prompt_navigation_layout = '''        const transcriptFrame = new TuiLayouts.VStack([
            { component: this.promptNavigationTopBar, basis: "auto", grow: 0, shrink: 0, minSize: 0 },
            { component: this.transcriptScrollView, basis: 0, grow: 1, shrink: 1, minSize: 1 },
            { component: this.promptNavigationBottomBar, basis: "auto", grow: 0, shrink: 0, minSize: 0 },
        ]);
        this.fullscreenLayoutRoot = new TuiLayouts.VStack([
            { component: transcriptFrame, basis: 0, grow: 1, shrink: 1, minSize: 1 },
            { component: dock, basis: "auto", grow: 0, shrink: 1, minSize: 1 },
        ]);'''
    if native_fullscreen_layout in text:
        text = text.replace(native_fullscreen_layout, prompt_navigation_layout, 1)
    elif prompt_navigation_layout not in text:
        raise SystemExit("Could not anchor native fullscreen layout for prompt-navigation bars")

    text = patch_clipboard_image_attachments(text)

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
        'getPromptNavigationState(width, refresh = false)',
        'renderPromptNavigationBar(direction, width, refresh = false)',
        'promptNavigationStateCache = undefined',
        'navigatePromptBar(direction)',
        'handleInteractiveUrl(url)',
        'pi://prompt-navigation/previous',
        'pi://prompt-navigation/next',
        'Symbol.for("pi-local-mods.action-handlers")',
        'url.startsWith("pi-local://")',
        'component: this.promptNavigationTopBar',
        'component: this.promptNavigationBottomBar',
        'openUrl: (url) => this.handleInteractiveUrl(url)',
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

def patch_tui_unicode_width() -> None:
    """Measure non-emoji graphemes by normalized printable codepoint widths."""
    marker = CLEAN_MARKERS["TUI_UTILS"]
    backup(TUI_UTILS, marker)
    text = clean_source(TUI_UTILS, marker).read_text()
    zero_width_needle = '''const zeroWidthRegex = /^(?:\\p{Default_Ignorable_Code_Point}|\\p{Control}|\\p{Mark}|\\p{Surrogate})+$/v;'''
    zero_width_replacement = '''const zeroWidthRegex = /^(?:\\p{Default_Ignorable_Code_Point}|\\p{Control}|\\p{Nonspacing_Mark}|\\p{Enclosing_Mark}|\\p{Surrogate})+$/v;'''
    if text.count(zero_width_needle) != 1:
        raise SystemExit("Could not anchor pi-tui zero-width mark classification")
    text = text.replace(zero_width_needle, zero_width_replacement, 1)
    signature = "function graphemeWidth(segment) {"
    if text.count(signature) != 1:
        raise SystemExit("Could not anchor pi-tui grapheme width patch")
    replacement = '''function graphemeWidth(segment) {
    if (segment === "\\t") {
        return 3;
    }
    // Zero-width clusters
    if (zeroWidthRegex.test(segment)) {
        return 0;
    }
    // Emoji check with pre-filter
    if (couldBeEmoji(segment) && rgiEmojiRegex.test(segment)) {
        return 2;
    }
    // [pi-local-mods] Match Ghostty's cell advance for complex graphemes.
    // NFC first composes Hangul and ordinary base+mark sequences. For every
    // remaining non-emoji cluster, sum all printable codepoints rather than only
    // the first base. Unicode spacing marks advance a cell in Ghostty, while
    // nonspacing/enclosing marks remain zero-width. Ghostty allocates at most
    // two cells to one grapheme. This handles Indic text without script lists.
    const normalized = segment.normalize("NFC");
    let width = 0;
    for (const char of normalized) {
        if (zeroWidthRegex.test(char))
            continue;
        const cp = char.codePointAt(0);
        if (cp >= 0x1f1e6 && cp <= 0x1f1ff)
            width += 2;
        else
            width += eastAsianWidth(cp);
    }
    return Math.min(width, 2);
}'''
    text = replace_js_method(text, signature, replacement)
    TUI_UTILS.write_text(text)


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
        "await execLeanCtx(pi, args, { signal });",
        "await execLeanCtx(pi, args, { signal, cwd: ctx.cwd });",
        "ctx_read CLI fallbacks",
        expected=2,
    )
    index = replace_required(index,
        'await execLeanCtx(pi, ["ls", absolutePath], { signal });',
        'await execLeanCtx(pi, ["ls", absolutePath], { signal, cwd: ctx.cwd });',
    )
    index = replace_required(index,
        'await execLeanCtx(pi, ["find", params.pattern, absolutePath], { signal });',
        'await execLeanCtx(pi, ["find", params.pattern, absolutePath], { signal, cwd: ctx.cwd });',
    )
    index = replace_required(index,
        'const result = await pi.exec(bin, ["-c", ...searchArgs], { signal });',
        'const result = await pi.exec(bin, ["-c", ...searchArgs], { signal, cwd: ctx.cwd });',
    )
    index = replace_required(index,
        '''    async execute(_toolCallId, params, signal) {
      const output = await execLeanCtx(pi, params.args, { signal });''',
        '''    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const output = await execLeanCtx(pi, params.args, { signal, cwd: ctx.cwd });''',
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
      // Non-blocking: do not delay session startup on the MCP child connecting.
      void mcpBridge.start(pi).catch((err: unknown) => {
        console.error(`[pi-lean-ctx] MCP bridge startup failed: ${err}`);
      });
    });

    pi.on("session_shutdown", async () => {
      const bridge = mcpBridge;
      mcpBridge = null;
      await bridge?.shutdown();
    });''',
    )
    index = replace_required(index,
        '''
    void mcpBridge.start(pi).catch((err: unknown) => {
      console.error(`[pi-lean-ctx] MCP bridge startup failed: ${err}`);
    });
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
        "execLeanCtx(pi, params.args, { signal, cwd: ctx.cwd })",
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


def install_extensions() -> None:
    extension_dir = PI_AGENT_DIR / "extensions"
    extension_dir.mkdir(parents=True, exist_ok=True)
    for source in EXTENSION_SOURCES:
        if not source.exists():
            raise SystemExit(f"extension source missing: {source}")
        shutil.copy2(source, extension_dir / source.name)


def verify() -> None:
    paths = [INTERACTIVE, CLIPBOARD_IMAGE, FOOTER, CUSTOM_EDITOR, TUI_UTILS]
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
    patch_tui_unicode_width()
    patch_lean_ctx_session_cwd()
    patch_bg_tasks_shortcuts()
    install_theme()
    install_extensions()
    verify()
    print("Applied pi-local-mods. Restart pi to use the patched runtime.")


if __name__ == "__main__":
    main()
