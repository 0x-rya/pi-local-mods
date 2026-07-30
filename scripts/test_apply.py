#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APPLY_PATH = ROOT / "scripts" / "apply.py"
FIXTURES = ROOT / "tests/fixtures"
PI_FIXTURE = FIXTURES / "pi"
AGENT_FIXTURE = FIXTURES / "agent"


def load_apply_module():
    spec = importlib.util.spec_from_file_location("pi_local_mods_apply", APPLY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ApplyPatchResultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mod = load_apply_module()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def copy_fixture(self, source: Path, relative: str) -> Path:
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def assertNodeChecks(self, path: Path) -> None:
        # Validates that a patched JS file is at least syntactically valid.
        # Skipped when node isn't installed (e.g. a plain Python env).
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"{path} failed node --check:\n{result.stderr}")

    def assertNodeScript(self, script: str) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        result = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"node behavior check failed:\n{result.stdout}\n{result.stderr}")

    def test_interactive_patch_final_result(self) -> None:
        source = PI_FIXTURE / "dist/modes/interactive/interactive-mode.js"
        source_text = source.read_text()
        self.assertNotIn("class FixedBottomScrollLayout {", source_text)
        self.assertIn("this.ui.addChild(this.chatContainer);", source_text)
        interactive = self.copy_fixture(
            source,
            "pi/dist/modes/interactive/interactive-mode.js",
        )
        self.mod.INTERACTIVE = interactive

        self.mod.patch_interactive()
        text = interactive.read_text()

        self.assertIn('sliceByColumn, truncateToWidth, } from "@earendil-works/pi-tui";', text)
        self.assertIn("class FixedBottomScrollLayout {", text)
        self.assertIn("this.fixedLayout = new FixedBottomScrollLayout(this.ui", text)
        self.assertEqual(text.count("this.fixedLayout = new FixedBottomScrollLayout(this.ui"), 1)
        self.assertIn("this.ui.addChild(this.fixedLayout);", text)
        self.assertNotIn("this.ui.addChild(this.chatContainer);", text)
        self.assertIn("this.ui.addInputListener((data) => this.fixedLayout?.handleInput(data));", text)
        self.assertIn("this.ui.addInputListener((data) => this.handleCapturedTerminalLogInput(data));", text)
        self.assertIn("bottomBorderWidgetStatus = \"\";", text)
        self.assertIn("bottomBorderWidgetLimits = \"\";", text)
        self.assertIn("compactLeanCtxStatus(text)", text)
        self.assertIn("compactLimitsStatus(text)", text)
        self.assertIn("refreshBottomBorderWidgetStatus(width)", text)
        self.assertIn("renderBottomBorderWidgetStatusLine(width)", text)
        self.assertIn("moveBottomWidgetStatusToEditorBorder(lines)", text)
        # ctrl+o (toggle tool output) must anchor the top visible transcript
        # line instead of letting the viewport jump.
        self.assertIn("const applyExpansion = () => {", text)
        self.assertIn("this.fixedLayout.preserveScrollAnchor(applyExpansion);", text)
        self.assertEqual(text.count("this.fixedLayout.preserveScrollAnchor(applyExpansion);"), 1)
        self.assertIn('this.showStatus(`Tool output: ${expanded ? "expanded" : "collapsed"}`);', text)
        self.assertEqual(text.count('this.showStatus(`Tool output: ${expanded ? "expanded" : "collapsed"}`);'), 1)
        # Pinned "previous message" jump bar at the top of the transcript.
        self.assertIn("renderScrollLinesWithSpans(width)", text)
        self.assertIn("firstMeaningfulLine(childLines)", text)
        self.assertIn("grandChild instanceof UserMessageComponent", text)
        self.assertIn("findPreviousMessage(this.messageSpans, viewportTopContentLine)", text)
        self.assertIn("findNextMessage(this.messageSpans, nextThreshold)", text)
        self.assertIn("const aboveCount = start;", text)
        self.assertIn("const belowCount = this.scrollOffset;", text)
        self.assertIn('theme.fg("warning", belowTag)', text)
        self.assertIn("this.topMessageTarget = prev.start;", text)
        self.assertIn("this.bottomMessageTarget = next.start;", text)
        self.assertIn("row === this.lastBottomBarRow", text)
        self.assertIn("scrollToMessageStart(this.topMessageTarget)", text)
        self.assertIn("this.chatContainer = chatContainer ?? scrollChildren[2];", text)
        self.assertIn("const trimmedPlain = plain.trimStart();", text)
        self.assertIn("/^Limits\\s*[|│]/", text)
        self.assertIn("/^\\s*Limits\\s*[|│]\\s*/", text)
        self.assertIn("coalesceQuotaDashboardLines(lines)", text)
        self.assertIn("quotaDashboardLines(component, width)", text)
        self.assertIn('const component = this.extensionWidgetsBelow.get("quota-dashboard");', text)
        self.assertIn("return this.coalesceQuotaDashboardLines(component?.render(width) ?? []);", text)
        self.assertIn("The editor bottom-border provider owns this widget.", text)
        self.assertNotIn("Math.max(width, 4096)", text)
        self.assertIn("this.defaultEditor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? \"\");", text)
        self.assertIn("this.editor.setBottomBorderProvider?.((width) => this.renderBottomBorderWidgetStatusLine?.(width) ?? \"\");", text)
        self.assertNotIn("setBottomBorderProvider?.((width) => this.footer.renderExtensionStatusLine?.(width)", text)
        self.assertNotIn("setBottomBorderProvider?.((width) => this.footer.renderExtensionStatusBorderLine?.(width)", text)
        self.assertIn("installTerminalOutputGuard()", text)
        self.assertIn("terminalLogContainer;", text)
        self.assertIn("capturedTerminalLogHitRegions.push({ type: \"copy\"", text)
        self.assertIn("const priority = { copy: 0, close: 1, clear: 1, toggle: 2 };", text)
        self.assertIn("capturedTerminalLogHitRegions.push({ type: \"toggle\", id: entry.id, row, startCol: 0", text)
        self.assertIn("const submission = await this.prepareClipboardImageSubmission(text);", text)
        self.assertNotIn("const submission = this.prepareClipboardImageSubmission(text);", text)
        self.assertNodeChecks(interactive)

        # Re-applying must not accumulate duplicate injected methods.
        first_apply = interactive.read_bytes()
        self.mod.patch_interactive()
        self.assertEqual(interactive.read_bytes(), first_apply)
        reapplied = interactive.read_text()
        self.assertEqual(reapplied.count("    stripStatusAnsi(text) {"), 1)
        self.assertEqual(reapplied.count("    coalesceQuotaDashboardLines(lines) {"), 1)
        self.assertEqual(reapplied.count("    renderBottomBorderWidgetStatusLine(width) {"), 1)

    def test_interactive_patch_migrates_previous_status_implementation(self) -> None:
        source = PI_FIXTURE / "dist/modes/interactive/interactive-mode.js"
        fresh = self.copy_fixture(source, "fresh/interactive-mode.js")
        legacy = self.copy_fixture(source, "legacy/interactive-mode.js")

        self.mod.INTERACTIVE = fresh
        self.mod.patch_interactive()
        expected = fresh.read_bytes()

        self.mod.INTERACTIVE = legacy
        self.mod.patch_interactive()
        legacy_text = legacy.read_text()
        block_start = legacy_text.index("    stripStatusAnsi(text) {")
        block_end = legacy_text.index("    renderWidgets() {", block_start)
        current_block = legacy_text[block_start:block_end]
        # The previous patch could accumulate duplicate methods and used a
        # finite-width quota probe inside renderWidgetContainer().
        legacy_text = legacy_text[:block_start] + current_block + current_block + legacy_text[block_end:]
        old_container = r'''    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {
        container.clear();
        for (const [id, component] of widgets.entries()) {
            container.addChild({
                render: (width) => id === "quota-dashboard"
                    ? this.moveBottomWidgetStatusToEditorBorder(component.render(Math.max(width, 4096)))
                    : component.render(width),
                invalidate: () => component.invalidate?.(),
            });
        }
    }'''
        legacy_text = self.mod.replace_js_method(
            legacy_text,
            "    renderWidgetContainer(container, widgets, spacerWhenEmpty, leadingSpacer) {",
            old_container,
        )
        legacy.write_text(legacy_text)

        self.mod.patch_interactive()
        self.assertEqual(legacy.read_bytes(), expected)
        migrated = legacy.read_text()
        self.assertNotIn("Math.max(width, 4096)", migrated)
        self.assertEqual(migrated.count("    stripStatusAnsi(text) {"), 1)

    def test_interactive_patch_repairs_legacy_unawaited_clipboard_submission(self) -> None:
        source = PI_FIXTURE / "dist/modes/interactive/interactive-mode.js"
        interactive = self.copy_fixture(
            source,
            "pi/dist/modes/interactive/interactive-mode.js",
        )
        self.mod.INTERACTIVE = interactive

        self.mod.patch_interactive()
        patched_text = interactive.read_text()
        awaited_call = "const submission = await this.prepareClipboardImageSubmission(text);"
        unawaited_call = "const submission = this.prepareClipboardImageSubmission(text);"
        self.assertIn(awaited_call, patched_text)

        broken_text = patched_text.replace(awaited_call, unawaited_call)
        self.assertIn(unawaited_call, broken_text)
        interactive.write_text(broken_text)

        self.mod.patch_interactive()
        repaired_text = interactive.read_text()
        self.assertNotIn(unawaited_call, repaired_text)
        self.assertEqual(repaired_text.count(awaited_call), patched_text.count(awaited_call))

    def test_quota_dashboard_resize_behavior(self) -> None:
        source = PI_FIXTURE / "dist/modes/interactive/interactive-mode.js"
        interactive = self.copy_fixture(source, "pi/dist/modes/interactive/interactive-mode.js")
        self.mod.INTERACTIVE = interactive
        self.mod.patch_interactive()
        text = interactive.read_text()
        start = text.index("    stripStatusAnsi(text) {")
        end = text.index("    renderWidgets() {", start)
        methods = text[start:end]

        pi_tui = self.mod.PI_PACKAGE / "node_modules/@earendil-works/pi-tui/dist/index.js"
        if not pi_tui.exists():
            self.skipTest("installed pi-tui is required for real display-width behavior checks")
        script = (
            f'import {{ Container, Text, truncateToWidth, visibleWidth }} from {json.dumps(pi_tui.as_uri())};\n'
            'import { stripVTControlCharacters as stripAnsi } from "node:util";\n'
            + r'''
const theme = {
  fg: (_color, text) => `\x1b[36m${text}\x1b[0m`,
  bold: (text) => text,
};
const assert = (condition, message) => { if (!condition) throw new Error(message); };
class Harness {
  constructor() {
    this.bottomBorderWidgetStatus = "";
    this.bottomBorderWidgetLimits = "";
    this.extensionWidgetsBelow = new Map();
  }
''' + methods + r'''}

let quotaRenderCalls = 0;
let unrelatedRenderCalls = 0;
const dashboardLines = [
  "\x1b[35mLimits\x1b[0m │ Codex 5h: 84% left (in 2h) · wk: 100% left (in 5d 18h) │ 模型👩‍💻é 5h: — · wk: —",
  "\x1b[35mActive\x1b[0m │ openai-codex/gpt │ lean-ctx on saved 55.7M tok 81.9% $141.82",
];
const quotaContainer = new Container();
for (const line of dashboardLines) quotaContainer.addChild(new Text(line, 1, 0));
const quota = {
  render(width) { quotaRenderCalls++; return quotaContainer.render(width); },
};
const unrelated = { render() { unrelatedRenderCalls++; return ["other widget"]; } };
const harness = new Harness();
harness.extensionWidgetsBelow = new Map([["quota-dashboard", quota], ["other", unrelated]]);
const rendered = [];
for (const width of [160, 72, 5, 4, 3, 2, 1, 0, 160]) {
  const line = harness.renderBottomBorderWidgetStatusLine(width);
  rendered.push(stripAnsi(line));
  assert(visibleWidth(line) <= width, `line exceeded ${width}: ${visibleWidth(line)}`);
  assert(!stripAnsi(line).includes("\x1b"), "render left an unterminated/unsupported escape sequence");
  if (width >= 72) {
    assert(harness.bottomBorderWidgetStatus.includes("$141.82"), "lean-ctx cost was orphaned");
    assert(harness.bottomBorderWidgetLimits.includes("Codex"), "limits row was lost");
  }
}
assert(rendered[0] === rendered[rendered.length - 1], "wide → narrow → wide output was unstable");
assert(quotaRenderCalls === 8, `quota Text container rendered ${quotaRenderCalls} times instead of once per positive-width border pass`);
assert(unrelatedRenderCalls === 0, "border refresh rendered an unrelated widget");

const legacy = {
  render() {
    return [
      "Limits │ Codex 5h: 84% left (in 2h)",
      "· wk: 100% left (in 5d 18h)",
      "Active │ openai-codex/gpt │ lean-ctx on saved",
      "55.7M tok 81.9% $141.82",
    ];
  },
};
const fallback = harness.quotaDashboardLines(legacy, 32);
assert(fallback.statusLines.length === 2, "wrapped legacy rows were not coalesced");
harness.bottomBorderWidgetStatus = "";
harness.bottomBorderWidgetLimits = "";
assert(harness.moveBottomWidgetStatusToEditorBorder(fallback.statusLines).length === 0, "status fragments leaked");
assert(harness.bottomBorderWidgetStatus.includes("$141.82"), "coalesced cost was lost");
'''
        )
        self.assertNodeScript(script)

    def test_footer_resize_behavior(self) -> None:
        methods = self.mod.FOOTER_RENDER_METHOD
        pi_tui = self.mod.PI_PACKAGE / "node_modules/@earendil-works/pi-tui/dist/index.js"
        if not pi_tui.exists():
            self.skipTest("installed pi-tui is required for real display-width behavior checks")
        script = (
            f'import {{ truncateToWidth, visibleWidth }} from {json.dumps(pi_tui.as_uri())};\n'
            'import { stripVTControlCharacters as stripAnsi } from "node:util";\n'
            + r'''
const theme = {
  fg: (_color, text) => `\x1b[36m${text}\x1b[0m`,
  bold: (text) => text,
};
const createUsageTotals = () => ({ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cost: 0 });
const addUsageToTotals = (totals, usage) => {
  for (const key of ["input", "output", "cacheRead", "cacheWrite"]) totals[key] += usage[key] ?? 0;
  totals.cost += usage.cost?.total ?? 0;
};
const formatTokens = (count) => count >= 1000000 ? `${(count / 1000000).toFixed(1)}M` : count >= 1000 ? `${Math.round(count / 1000)}k` : `${count}`;
const formatCwdForFooter = (cwd, home) => cwd.startsWith(home) ? `~${cwd.slice(home.length)}` : cwd;
const areExperimentalFeaturesEnabled = () => false;
const sanitizeStatusText = (text) => text;
const assert = (condition, message) => { if (!condition) throw new Error(message); };
class FooterHarness {
  constructor(session, footerData) {
    this.session = session;
    this.footerData = footerData;
    this.autoCompactEnabled = true;
    this.mainLineVisible = true;
  }
''' + methods + r'''}
const usage = { input: 100000, output: 92000, cacheRead: 33000000, cacheWrite: 12000, cost: { total: 141.82 } };
const session = {
  state: {
    model: {
      provider: "openai-codex",
      id: "gpt-very-long-model-name-that-must-be-dropped-before-important-token-fields-are-clipped",
      contextWindow: 272000,
      reasoning: true,
    },
    thinkingLevel: "high",
  },
  sessionManager: {
    getEntries: () => [{ type: "message", message: { role: "assistant", usage } }],
    getCwd: () => "/Users/test/home/jkdb/模型👩‍💻é",
    getSessionName: () => undefined,
  },
  getContextUsage: () => ({ contextWindow: 272000, percent: 43 }),
  modelRuntime: { isUsingOAuth: () => false },
};
const footerData = {
  getGitBranch: () => "main",
  getExtensionStatuses: () => new Map(),
};
const footer = new FooterHarness(session, footerData);
const wide = footer.renderMainStatusLine(260);
const medium = footer.renderMainStatusLine(165);
const narrow = footer.renderMainStatusLine(72);
const wideAgain = footer.renderMainStatusLine(260);
const extreme = [0, 1, 2, 3, 4, 5].map((width) => [width, footer.renderMainStatusLine(width)]);
for (const [width, line] of [[260, wide], [165, medium], [72, narrow], ...extreme]) {
  assert(visibleWidth(line) <= width, `footer exceeded ${width}: ${visibleWidth(line)}`);
  assert(!stripAnsi(line).includes("\x1b"), "footer left an unterminated/unsupported escape sequence");
}
assert(stripAnsi(wide) === stripAnsi(wideAgain), "wide → narrow → wide footer was unstable");
assert(stripAnsi(wide).includes("ai openai-codex/"), "wide footer unexpectedly dropped the model");
assert(!stripAnsi(medium).includes("ai openai-codex/"), "medium footer kept the model instead of complete metrics");
assert(stripAnsi(medium).includes("CH99.7%"), "cache-hit metric was clipped mid-field");
assert(stripAnsi(medium).includes("$141.820"), "cost metric was clipped mid-field");
assert(!stripAnsi(medium).includes("…"), "medium footer used character truncation unnecessarily");
assert(!stripAnsi(narrow).includes("…"), "narrow footer failed to drop whole optional fields");
'''
        )
        self.assertNodeScript(script)

    def test_quota_dashboard_extension_factory(self) -> None:
        pi_package = self.mod.PI_PACKAGE
        pi_tui = pi_package / "node_modules/@earendil-works/pi-tui/dist/index.js"
        jiti = pi_package / "node_modules/jiti/lib/jiti-static.mjs"
        extension = ROOT / "extensions/quota-dashboard.ts"
        if not pi_tui.exists() or not jiti.exists():
            self.skipTest("installed Pi + jiti are required for extension integration checks")

        home = self.root / "extension-home"
        auth = home / ".pi/agent/auth.json"
        auth.parent.mkdir(parents=True)
        auth.write_text('{"openai-codex":{"key":"test"}}')
        script = f'''
import {{ createJiti }} from {json.dumps(jiti.as_uri())};
import {{ Container, Text, visibleWidth }} from {json.dumps(pi_tui.as_uri())};
process.env.HOME = {json.dumps(str(home))};
const assert = (condition, message) => {{ if (!condition) throw new Error(message); }};
const jiti = createJiti(import.meta.url, {{
  moduleCache: false,
  alias: {{ "@earendil-works/pi-tui": {json.dumps(str(pi_tui))} }},
}});
const factory = await jiti.import({json.dumps(str(extension))}, {{ default: true }});
assert(typeof factory === "function", "extension did not load as a factory");
const handlers = new Map();
const pi = {{
  on(name, handler) {{ handlers.set(name, handler); }},
  registerShortcut() {{}},
  registerCommand() {{}},
  getThinkingLevel() {{ return "high"; }},
  setThinkingLevel() {{}},
  sendUserMessage() {{}},
}};
factory(pi);
assert(handlers.has("model_select"), "model_select handler was not registered");
const widgetUpdates = [];
const theme = {{
  fg: (_color, text) => `\x1b[36m${{text}}\x1b[0m`,
  bold: (text) => text,
}};
const ctx = {{
  hasUI: true,
  model: {{ provider: "openai-codex", id: "gpt-test" }},
  ui: {{
    theme,
    setWidget(id, value, options) {{ widgetUpdates.push({{ id, value, options }}); }},
  }},
}};
await handlers.get("model_select")({{}}, ctx);
await handlers.get("model_select")({{}}, ctx);
assert(widgetUpdates.length === 2, "widget replacement did not publish twice");
for (const update of widgetUpdates) {{
  assert(update.id === "quota-dashboard", "wrong widget id");
  assert(update.options?.placement === "belowEditor", "wrong widget placement");
  assert(Array.isArray(update.value), "widget did not use the documented string-array API");
  assert(update.value.length === 2, "dashboard did not publish two logical rows");
  const component = new Container();
  for (const line of update.value) component.addChild(new Text(line, 1, 0));
  for (const width of [8, 40, 72, 160]) {{
    const lines = component.render(width);
    assert(lines.length > 0, `Text container rendered no rows at ${{width}}`);
    for (const line of lines) {{
      assert(visibleWidth(line) <= width, `Text container exceeded ${{width}} columns`);
    }}
  }}
  component.invalidate();
  component.dispose?.();
}}
'''
        self.assertNodeScript(script)

    def test_terminal_patch_final_result(self) -> None:
        source = PI_FIXTURE / "node_modules/@earendil-works/pi-tui/dist/terminal.js"
        source_text = source.read_text()
        self.assertNotIn("?1002h", source_text)
        terminal = self.copy_fixture(
            source,
            "pi/node_modules/@earendil-works/pi-tui/dist/terminal.js",
        )
        self.mod.TERMINAL = terminal

        self.mod.patch_terminal()
        text = terminal.read_text()

        self.assertIn('process.stdout.write("\\x1b[?1002h\\x1b[?1006h");', text)
        self.assertIn('process.stdout.write("\\x1b[?1002l\\x1b[?1006l");', text)
        self.assertIn("Enable button-event mouse tracking with SGR encoding", text)
        self.assertNodeChecks(terminal)

    def test_tui_overlay_scroll_patch_final_result(self) -> None:
        source = PI_FIXTURE / "node_modules/@earendil-works/pi-tui/dist/tui.js"
        source_text = source.read_text()
        self.assertNotIn("[pi-local-mods] overlay full-redraw", source_text)
        self.assertIn(
            "const appendStart = appendedLines && firstChanged === this.previousLines.length && firstChanged > 0;",
            source_text,
        )
        tui = self.copy_fixture(
            source,
            "pi/node_modules/@earendil-works/pi-tui/dist/tui.js",
        )
        self.mod.TUI_JS = tui

        self.mod.patch_tui_overlay_scroll()
        text = tui.read_text()

        self.assertIn("[pi-local-mods] overlay full-redraw on appended content", text)
        self.assertEqual(text.count("[pi-local-mods] overlay full-redraw on appended content"), 1)
        self.assertIn(
            "if (firstChanged !== -1 && this.overlayStack.some((entry) => this.isOverlayVisible(entry))) {",
            text,
        )
        self.assertIn('logRedraw("overlay active + changed frame");', text)
        # The guard must sit between the appendStart line and the "No changes"
        # early return so it short-circuits the differential writer.
        self.assertLess(
            text.index("const appendStart = appendedLines"),
            text.index("[pi-local-mods] overlay full-redraw on appended content"),
        )
        self.assertLess(
            text.index("[pi-local-mods] overlay full-redraw on appended content"),
            text.index("// No changes - but still need to update hardware cursor position if it moved"),
        )
        self.assertNodeChecks(tui)

        # Re-applying must be a no-op (idempotent) and must not duplicate the guard.
        first_apply = tui.read_bytes()
        self.mod.patch_tui_overlay_scroll()
        self.assertEqual(tui.read_bytes(), first_apply)

    def test_footer_patch_final_result(self) -> None:
        source = PI_FIXTURE / "dist/modes/interactive/components/footer.js"
        self.assertNotIn("renderMainStatusLine", source.read_text())
        footer = self.copy_fixture(source, "pi/dist/modes/interactive/components/footer.js")
        self.mod.FOOTER = footer

        self.mod.patch_footer_component()
        text = footer.read_text()

        self.assertIn("mainLineVisible = true;", text)
        self.assertIn("setMainLineVisible(visible)", text)
        self.assertIn("renderMainStatusLine(width)", text)
        self.assertIn('labelled("git", branch, "warning")', text)
        self.assertIn('parts.push(labelled("ai", modelDisplay, "accent"))', text)
        self.assertIn("const candidates = [buildRight(tokenParts.length, true), buildRight(tokenParts.length, false)]", text)
        self.assertIn("candidates.push(buildRight(tokenCount, false))", text)
        self.assertIn("right = buildRight(0, false)", text)
        self.assertIn("if (this.mainLineVisible !== false)", text)
        self.assertNodeChecks(footer)

    def test_custom_editor_patch_final_result(self) -> None:
        source = PI_FIXTURE / "dist/modes/interactive/components/custom-editor.js"
        self.assertNotIn("setTopBorderProvider", source.read_text())
        editor = self.copy_fixture(source, "pi/dist/modes/interactive/components/custom-editor.js")
        self.mod.CUSTOM_EDITOR = editor

        self.mod.patch_custom_editor()
        text = editor.read_text()

        self.assertIn("topBorderProvider;", text)
        self.assertIn("bottomBorderProvider;", text)
        self.assertIn("setTopBorderProvider(provider)", text)
        self.assertIn("setBottomBorderProvider(provider)", text)
        self.assertIn("frameLine(line, width, left, right)", text)
        self.assertIn("const lines = super.render(width)", text)
        self.assertNodeChecks(editor)

    def test_clipboard_image_patch_final_result(self) -> None:
        source = PI_FIXTURE / "dist/utils/clipboard-image.js"
        self.assertNotIn("readClipboardImageViaMacOsFileUrl", source.read_text())
        clip = self.copy_fixture(source, "pi/dist/utils/clipboard-image.js")
        self.mod.CLIPBOARD_IMAGE = clip

        self.mod.patch_clipboard_image()
        text = clip.read_text()

        self.assertIn('import { extname, join } from "path";', text)
        self.assertIn("function readClipboardImageViaMacOsFileUrl()", text)
        self.assertIn("readClipboardImageViaMacOsFileUrl() ??", text)
        self.assertNodeChecks(clip)

    def test_install_hook_idempotent(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("install_hook", ROOT / "scripts" / "install_hook.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        rc = self.root / ".zshrc"
        hook = self.root / "pi-hook.sh"  # temp stand-in; must not touch the real file
        hook.write_text("# hook\n")

        self.assertEqual(mod.install(rc, hook), "installed")
        text = rc.read_text()
        self.assertIn("pi-hook.sh", text)
        self.assertIn(str(hook), text)
        self.assertTrue((self.root / ".zshrc.pi-local-mods.bak").exists())

        # Second call is a no-op (idempotent) and must not duplicate the block.
        before = rc.read_text()
        self.assertEqual(mod.install(rc, hook), "present")
        self.assertEqual(rc.read_text(), before)
        self.assertEqual(text.count("pi-hook.sh"), rc.read_text().count("pi-hook.sh"))

    def test_post_update_failure_format(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("post_update", ROOT / "scripts" / "post_update.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        msg = mod.format_failure(
            "apply.py - re-patching the updated Pi",
            "python3 scripts/apply.py",
            "/tmp/x.log",
            "==> step\nCould not apply footer pretty status patch: missing ['renderMainStatusLine(width)']\nTraceback\n",
            Path("/repo"),
        )
        self.assertIn("pi-local-mods: re-apply after `pi update` FAILED", msg)
        self.assertIn("│ step: apply.py", msg)
        self.assertIn("Could not apply footer pretty status patch", msg)
        self.assertIn("│ full log: /tmp/x.log", msg)
        self.assertIn("cd /repo && python3 scripts/apply.py", msg)
        self.assertIn("python3 scripts/refresh_fixtures.py", msg)

    def test_lean_ctx_session_cwd_patch_final_result(self) -> None:
        package = self.root / "agent/npm/node_modules/pi-lean-ctx"
        index_source = AGENT_FIXTURE / "npm/node_modules/pi-lean-ctx/extensions/index.ts"
        bridge_source = AGENT_FIXTURE / "npm/node_modules/pi-lean-ctx/extensions/mcp-bridge.ts"
        self.assertNotIn("[pi-local-mods]", index_source.read_text())
        self.assertNotIn("cwd: this.cwd", bridge_source.read_text())

        index = self.copy_fixture(
            index_source,
            "agent/npm/node_modules/pi-lean-ctx/extensions/index.ts",
        )
        bridge = self.copy_fixture(
            bridge_source,
            "agent/npm/node_modules/pi-lean-ctx/extensions/mcp-bridge.ts",
        )
        self.mod.LEAN_CTX_PACKAGE = package
        self.mod.LEAN_CTX_INDEX = index
        self.mod.LEAN_CTX_MCP_BRIDGE = bridge

        self.mod.patch_lean_ctx_session_cwd()
        index_text = index.read_text()
        bridge_text = bridge.read_text()

        self.assertIn("[pi-local-mods] Bind all session-scoped work to ctx.cwd", index_text)
        self.assertIn('pi.on("session_start", async (_event, ctx) => {', index_text)
        self.assertIn("if (mcpBridge) return;", index_text)
        self.assertIn(
            "new McpBridge(resolveBinary(), PI_CONFIG.forwardedEnv, {\n        cwd: ctx.cwd,",
            index_text,
        )
        # MCP startup must stay non-blocking so it does not delay session_start.
        self.assertIn("void mcpBridge.start(pi).catch((err: unknown) => {", index_text)
        self.assertEqual(index_text.count("void mcpBridge.start(pi).catch"), 1)
        self.assertNotIn("mcpBridge = enableMcpBridge\n    ? new McpBridge", index_text)
        self.assertIn("createCompressedBashTool(ctx.cwd)", index_text)
        self.assertIn("createReadToolDefinition(ctx.cwd).execute", index_text)
        self.assertIn("execLeanCtx(pi, params.args, { signal, cwd: ctx.cwd })", index_text)
        self.assertIn("{ signal, cwd: ctx.cwd }", index_text)
        self.assertIn("[pi-local-mods] Pin the MCP child to the active session cwd", bridge_text)
        self.assertIn("  cwd?: string;", bridge_text)
        self.assertIn("    this.cwd = policy.cwd ?? process.cwd();", bridge_text)
        self.assertIn("      cwd: this.cwd,", bridge_text)
        self.assertIn("[pi-local-mods] An intentional close must not also schedule", bridge_text)
        self.assertIn("if (transport) transport.onclose = undefined;", bridge_text)
        self.assertIn("private reconnectPromise: Promise<void> | undefined;", bridge_text)
        self.assertIn("if (this.reconnectPromise) return this.reconnectPromise;", bridge_text)
        self.assertIn("this.reconnectPromise = reconnect;", bridge_text)
        # Constructor arity is unchanged: old/new index and bridge files remain
        # mutually compatible if an update is interrupted between replacements.
        self.assertIn(
            "  constructor(\n    binary: string,\n    extraEnv: Record<string, string> = {},",
            bridge_text,
        )
        self.assertNodeChecks(index)
        self.assertNodeChecks(bridge)

        # Re-applying must be a no-op and must retain clean backups for future
        # package upgrades/drift checks.
        first_index = index_text
        first_bridge = bridge_text
        self.mod.patch_lean_ctx_session_cwd()
        self.assertEqual(index.read_text(), first_index)
        self.assertEqual(bridge.read_text(), first_bridge)
        self.assertNotIn(
            "[pi-local-mods]",
            index.with_suffix(index.suffix + ".pi-local-mods.bak").read_text(),
        )
        self.assertNotIn(
            "[pi-local-mods]",
            bridge.with_suffix(bridge.suffix + ".pi-local-mods.bak").read_text(),
        )

    def test_lean_ctx_patch_rejects_drift_without_partial_write(self) -> None:
        index_source = AGENT_FIXTURE / "npm/node_modules/pi-lean-ctx/extensions/index.ts"
        bridge_source = AGENT_FIXTURE / "npm/node_modules/pi-lean-ctx/extensions/mcp-bridge.ts"
        cases = [
            (
                "index-startup-anchor",
                "index",
                "[pi-lean-ctx] MCP bridge startup failed:",
                "[pi-lean-ctx] changed startup wording:",
            ),
            (
                "bridge-cwd-assignment-anchor",
                "bridge",
                "    this.binary = binary;\n    this.extraEnv = extraEnv;",
                "    this.binary = binary;\n    // upstream drift\n    this.extraEnv = extraEnv;",
            ),
        ]

        for name, target_name, old, new in cases:
            with self.subTest(name=name):
                package = self.root / name / "pi-lean-ctx"
                index = package / "extensions/index.ts"
                bridge = package / "extensions/mcp-bridge.ts"
                index.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(index_source, index)
                shutil.copy2(bridge_source, bridge)
                target = index if target_name == "index" else bridge
                original_target = target.read_text()
                self.assertEqual(original_target.count(old), 1)
                target.write_text(original_target.replace(old, new))
                before_index = index.read_text()
                before_bridge = bridge.read_text()

                self.mod.LEAN_CTX_PACKAGE = package
                self.mod.LEAN_CTX_INDEX = index
                self.mod.LEAN_CTX_MCP_BRIDGE = bridge
                with self.assertRaises(SystemExit):
                    self.mod.patch_lean_ctx_session_cwd()

                # Strict anchor validation happens before staged replacement, so
                # neither member of the two-file patch may be partially updated.
                self.assertEqual(index.read_text(), before_index)
                self.assertEqual(bridge.read_text(), before_bridge)
                self.assertFalse(list(index.parent.glob(".*.pi-local-mods.*.ts")))

    def test_lean_ctx_patch_rolls_back_if_second_replace_fails(self) -> None:
        package = self.root / "rollback" / "pi-lean-ctx"
        index = package / "extensions/index.ts"
        bridge = package / "extensions/mcp-bridge.ts"
        index.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            AGENT_FIXTURE / "npm/node_modules/pi-lean-ctx/extensions/index.ts",
            index,
        )
        shutil.copy2(
            AGENT_FIXTURE / "npm/node_modules/pi-lean-ctx/extensions/mcp-bridge.ts",
            bridge,
        )
        before_index = index.read_text()
        before_bridge = bridge.read_text()
        self.mod.LEAN_CTX_PACKAGE = package
        self.mod.LEAN_CTX_INDEX = index
        self.mod.LEAN_CTX_MCP_BRIDGE = bridge

        real_replace = self.mod.os.replace
        replace_calls = 0

        def fail_second_replace(source, destination):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("injected second replace failure")
            return real_replace(source, destination)

        with mock.patch.object(self.mod.os, "replace", side_effect=fail_second_replace):
            with self.assertRaisesRegex(OSError, "injected second replace failure"):
                self.mod.patch_lean_ctx_session_cwd()

        self.assertEqual(index.read_text(), before_index)
        self.assertEqual(bridge.read_text(), before_bridge)
        self.assertFalse(list(index.parent.glob(".*.pi-local-mods.*.ts")))

    def test_bg_tasks_shortcut_patch_final_result(self) -> None:
        package = self.root / "agent/npm/node_modules/pi-patty-bg-tasks"
        shortcuts_source = AGENT_FIXTURE / "npm/node_modules/pi-patty-bg-tasks/src/shortcuts.ts"
        hint_source = AGENT_FIXTURE / "npm/node_modules/pi-patty-bg-tasks/src/hint.ts"
        self.assertIn('pi.registerShortcut("ctrl+b"', shortcuts_source.read_text())
        self.assertIn("ctrl+b to run in background", hint_source.read_text())
        shortcuts = self.copy_fixture(
            shortcuts_source,
            "agent/npm/node_modules/pi-patty-bg-tasks/src/shortcuts.ts",
        )
        hint = self.copy_fixture(
            hint_source,
            "agent/npm/node_modules/pi-patty-bg-tasks/src/hint.ts",
        )
        self.mod.BG_TASKS_PACKAGE = package
        self.mod.BG_TASKS_SHORTCUTS = shortcuts
        self.mod.BG_TASKS_HINT = hint

        self.mod.patch_bg_tasks_shortcuts()
        shortcuts_text = shortcuts.read_text()
        hint_text = hint.read_text()

        self.assertNotIn('pi.registerShortcut("ctrl+b"', shortcuts_text)
        self.assertIn('pi.registerShortcut("ctrl+shift+b"', shortcuts_text)
        self.assertIn("Ctrl+B is reserved by Pi's built-in editor", shortcuts_text)
        self.assertIn("ctrl+shift+b to run in background", hint_text)
        self.assertNotIn("ctrl+b to run in background", hint_text)


if __name__ == "__main__":
    unittest.main()
