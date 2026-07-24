#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

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
        self.assertIn("render: (width) => this.moveBottomWidgetStatusToEditorBorder(component.render(width))", text)
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
        self.assertIn('labelled("ai", modelDisplay, "accent")', text)
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
