import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { hyperlink, sliceByColumn, truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";
import { spawn } from "node:child_process";
import { format as formatConsoleArgs } from "node:util";

const ACTION_REGISTRY_SYMBOL = Symbol.for("pi-local-mods.action-handlers");
const ACTION_PREFIX = "pi-local://terminal-logs/";
const MAX_STORED_LOGS = 50;
const MAX_VISIBLE_LOGS = 8;
const MAX_EXPANDED_LINES = 6;

type ThemeLike = {
  fg(color: string, text: string): string;
};

type TerminalLog = {
  id: number;
  source: string;
  text: string;
  expanded: boolean;
};

type TerminalGuard = {
  originalStderrWrite: typeof process.stderr.write;
  originalConsoleError: typeof console.error;
  originalConsoleWarn: typeof console.warn;
  originalConsoleLog: typeof console.log;
  stderrWrite: typeof process.stderr.write;
  consoleError: typeof console.error;
  consoleWarn: typeof console.warn;
  consoleLog: typeof console.log;
};

type ActionHandler = (url: string) => boolean | void;

function getActionRegistry(): Map<string, ActionHandler> {
  const root = globalThis as any;
  const existing = root[ACTION_REGISTRY_SYMBOL];
  if (existing instanceof Map) return existing as Map<string, ActionHandler>;
  const registry = new Map<string, ActionHandler>();
  root[ACTION_REGISTRY_SYMBOL] = registry;
  return registry;
}

function sanitizeTerminalText(text: string): string {
  return text
    .replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b[_^PX][\s\S]*?(?:\x07|\x1b\\)/g, "")
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
}

export class TerminalLogController {
  private logs: TerminalLog[] = [];
  private partials = new Map<string, string>();
  private nextId = 1;
  private guard?: TerminalGuard;
  private renderTimer?: ReturnType<typeof setTimeout>;
  private active = false;
  private widgetInstalled = false;
  private ctx?: ExtensionContext;
  private tui?: { requestRender(): void };
  private theme?: ThemeLike;

  private readonly component = {
    render: (width: number) => this.render(width),
    invalidate: () => {},
  };

  private readonly actionHandler: ActionHandler = (url) => this.handleAction(url);

  start(ctx: ExtensionContext): void {
    if (ctx.mode !== "tui") return;
    this.ctx = ctx;
    this.active = true;
    getActionRegistry().set(ACTION_PREFIX, this.actionHandler);
    this.installGuard();
  }

  stop(ctx: ExtensionContext): void {
    this.active = false;
    if (this.renderTimer) clearTimeout(this.renderTimer);
    this.renderTimer = undefined;
    this.uninstallGuard();

    const registry = getActionRegistry();
    if (registry.get(ACTION_PREFIX) === this.actionHandler) registry.delete(ACTION_PREFIX);
    this.removeWidget(ctx);
    this.ctx = undefined;
    this.partials.clear();
  }

  clear(): void {
    this.logs = [];
    this.partials.clear();
    if (this.renderTimer) clearTimeout(this.renderTimer);
    this.renderTimer = undefined;
    this.requestRender();
  }

  getLogs(): readonly TerminalLog[] {
    return this.logs;
  }

  capture(source: string, text: string): void {
    if (!this.active) return;
    const sanitized = sanitizeTerminalText(text).replace(/\r/g, "\n");
    const combined = (this.partials.get(source) ?? "") + sanitized;
    const parts = combined.split("\n");
    let partial = parts.pop() ?? "";
    let changed = false;

    for (const part of parts) changed = this.addLine(source, part) || changed;
    if (partial.length > 4000) {
      changed = this.addLine(source, partial) || changed;
      partial = "";
    }
    if (partial) this.partials.set(source, partial);
    else this.partials.delete(source);
    if (changed || partial) this.scheduleRender();
  }

  private shouldCaptureOutput(): boolean {
    if (!this.active) return false;
    // Once Pi stops raw mode (external editor, suspension, or crash teardown),
    // output must reach the real terminal rather than an invisible TUI widget.
    return process.stdin.isTTY !== true || process.stdin.isRaw === true;
  }

  private installGuard(): void {
    if (this.guard) return;
    const originalStderrWrite = process.stderr.write;
    const originalConsoleError = console.error;
    const originalConsoleWarn = console.warn;
    const originalConsoleLog = console.log;
    const captureConsole = (source: string, args: unknown[]) => {
      this.capture(source, `${formatConsoleArgs(...args)}\n`);
    };
    const writeOriginalStderr = (chunk: any, encodingOrCallback?: any, callback?: any) => {
      if (encodingOrCallback === undefined) return originalStderrWrite.call(process.stderr, chunk);
      if (callback === undefined) return originalStderrWrite.call(process.stderr, chunk, encodingOrCallback);
      return originalStderrWrite.call(process.stderr, chunk, encodingOrCallback, callback);
    };
    const stderrWrite = ((chunk: any, encodingOrCallback?: any, callback?: any) => {
      if (!this.shouldCaptureOutput()) return writeOriginalStderr(chunk, encodingOrCallback, callback);
      const encoding = typeof encodingOrCallback === "string" ? encodingOrCallback : "utf8";
      this.capture("stderr", Buffer.isBuffer(chunk) ? chunk.toString(encoding) : String(chunk));
      const cb = typeof encodingOrCallback === "function" ? encodingOrCallback : callback;
      if (typeof cb === "function") process.nextTick(cb);
      return true;
    }) as typeof process.stderr.write;
    const consoleError = (...args: unknown[]) => this.shouldCaptureOutput()
      ? captureConsole("console.error", args)
      : originalConsoleError(...args);
    const consoleWarn = (...args: unknown[]) => this.shouldCaptureOutput()
      ? captureConsole("console.warn", args)
      : originalConsoleWarn(...args);
    const consoleLog = (...args: unknown[]) => this.shouldCaptureOutput()
      ? captureConsole("console.log", args)
      : originalConsoleLog(...args);

    process.stderr.write = stderrWrite;
    console.error = consoleError;
    console.warn = consoleWarn;
    console.log = consoleLog;
    this.guard = {
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

  private uninstallGuard(): void {
    const guard = this.guard;
    if (!guard) return;
    if (process.stderr.write === guard.stderrWrite) process.stderr.write = guard.originalStderrWrite;
    if (console.error === guard.consoleError) console.error = guard.originalConsoleError;
    if (console.warn === guard.consoleWarn) console.warn = guard.originalConsoleWarn;
    if (console.log === guard.consoleLog) console.log = guard.originalConsoleLog;
    this.guard = undefined;
  }

  private addLine(source: string, line: string): boolean {
    const text = line.trimEnd();
    if (!text) return false;
    this.logs.push({ id: this.nextId++, source, text, expanded: false });
    if (this.logs.length > MAX_STORED_LOGS) {
      this.logs.splice(0, this.logs.length - MAX_STORED_LOGS);
    }
    return true;
  }

  private flushPartials(): void {
    for (const [source, partial] of this.partials) this.addLine(source, partial);
    this.partials.clear();
  }

  private scheduleRender(): void {
    if (this.renderTimer) return;
    this.renderTimer = setTimeout(() => {
      this.renderTimer = undefined;
      this.flushPartials();
      this.requestRender();
    }, 75);
  }

  private ensureWidget(): void {
    if (this.widgetInstalled || !this.ctx) return;
    this.widgetInstalled = true;
    this.ctx.ui.setWidget("terminal-logs", (tui, theme) => {
      this.tui = tui;
      this.theme = theme as ThemeLike;
      return this.component;
    });
  }

  private removeWidget(ctx = this.ctx): void {
    if (!this.widgetInstalled || !ctx) return;
    this.widgetInstalled = false;
    ctx.ui.setWidget("terminal-logs", undefined);
    this.tui = undefined;
    this.theme = undefined;
  }

  private requestRender(): void {
    if (this.logs.length === 0) {
      this.removeWidget();
      return;
    }
    this.ensureWidget();
    this.component.invalidate();
    this.tui?.requestRender();
  }

  private remove(id: number): void {
    this.logs = this.logs.filter((entry) => entry.id !== id);
    this.requestRender();
  }

  private toggle(id: number): void {
    const entry = this.logs.find((item) => item.id === id);
    if (!entry) return;
    const expand = !entry.expanded;
    for (const item of this.logs) item.expanded = false;
    entry.expanded = expand;
    this.requestRender();
  }

  private copy(id: number): void {
    const entry = this.logs.find((item) => item.id === id);
    if (!entry) return;
    const child = spawn("pbcopy", [], { stdio: ["pipe", "ignore", "ignore"] });
    let settled = false;
    const fail = () => {
      if (settled) return;
      settled = true;
      this.ctx?.ui.notify("Could not copy terminal log", "error");
    };
    child.once("error", fail);
    child.stdin.once("error", fail);
    child.once("close", (code) => {
      if (settled) return;
      settled = true;
      this.ctx?.ui.notify(code === 0 ? "Terminal log copied" : "Could not copy terminal log", code === 0 ? "info" : "error");
    });
    child.stdin.end(`[${entry.source}] ${entry.text}`);
  }

  private handleAction(url: string): boolean {
    if (!url.startsWith(ACTION_PREFIX)) return false;
    const path = url.slice(ACTION_PREFIX.length);
    if (path === "clear") {
      this.clear();
      return true;
    }
    const [action, rawId] = path.split("/");
    const id = Number(rawId);
    if (!Number.isSafeInteger(id)) return true;
    if (action === "close") this.remove(id);
    else if (action === "toggle") this.toggle(id);
    else if (action === "copy") this.copy(id);
    return true;
  }

  private link(text: string, action: string): string {
    return hyperlink(text, `${ACTION_PREFIX}${action}`);
  }

  private wrapLine(text: string, width: number): string[] {
    if (width <= 0) return [];
    const lines: string[] = [];
    let remaining = text;
    while (visibleWidth(remaining) > width) {
      lines.push(sliceByColumn(remaining, 0, width, true));
      remaining = sliceByColumn(remaining, width, Math.max(0, visibleWidth(remaining) - width), true);
    }
    lines.push(remaining);
    return lines;
  }

  private render(width: number): string[] {
    const theme = this.theme;
    if (!theme || width <= 0 || this.logs.length === 0) return [];
    const shown = this.logs.slice(-MAX_VISIBLE_LOGS);
    const hidden = Math.max(0, this.logs.length - shown.length);
    const clearLabel = width >= 16 ? "[clear]" : "×";
    const clear = this.link(theme.fg("accent", clearLabel), "clear");
    const title = `Captured logs (${shown.length}${hidden ? ` shown, ${hidden} hidden` : ""})`;
    const titleWidth = Math.max(0, width - visibleWidth(clear) - 1);
    const headerTitle = truncateToWidth(theme.fg("warning", title), titleWidth, theme.fg("dim", "…"));
    const lines = [truncateToWidth(`${headerTitle} ${clear}`, width, theme.fg("dim", "…"))];

    for (const entry of shown) {
      const close = this.link(theme.fg("dim", "×"), `close/${entry.id}`);
      const summary = `${entry.source}: ${entry.text}`;
      if (!entry.expanded) {
        const prefixWidth = visibleWidth(close) + 1;
        const toggleText = truncateToWidth(
          theme.fg("warning", `▸ ${summary}`),
          Math.max(0, width - prefixWidth),
          theme.fg("dim", "…"),
        );
        lines.push(truncateToWidth(`${close} ${this.link(toggleText, `toggle/${entry.id}`)}`, width));
        continue;
      }

      const arrow = this.link(theme.fg("warning", "▾"), `toggle/${entry.id}`);
      const copy = this.link(theme.fg("accent", "[copy]"), `copy/${entry.id}`);
      const controlsWidth = visibleWidth(close) + visibleWidth(arrow) + visibleWidth(copy) + 3;
      const head = truncateToWidth(
        theme.fg("warning", summary),
        Math.max(0, width - controlsWidth),
        theme.fg("dim", "…"),
      );
      lines.push(truncateToWidth(`${close} ${arrow} ${copy} ${this.link(head, `toggle/${entry.id}`)}`, width));

      const bodyPrefix = theme.fg("dim", "  │ ");
      const bodyWidth = Math.max(1, width - visibleWidth(bodyPrefix));
      const wrapped = this.wrapLine(entry.text, bodyWidth);
      const visibleBody = wrapped.slice(0, MAX_EXPANDED_LINES);
      if (wrapped.length > MAX_EXPANDED_LINES) {
        visibleBody[MAX_EXPANDED_LINES - 1] = `… ${wrapped.length - MAX_EXPANDED_LINES + 1} more line(s)`;
      }
      for (const bodyLine of visibleBody) {
        const row = `${bodyPrefix}${theme.fg("warning", truncateToWidth(bodyLine, bodyWidth))}`;
        lines.push(this.link(truncateToWidth(row, width), `toggle/${entry.id}`));
      }
    }
    return lines;
  }
}

export default function terminalLogsExtension(pi: ExtensionAPI): void {
  const controller = new TerminalLogController();

  pi.on("session_start", (_event, ctx) => controller.start(ctx));
  pi.on("session_shutdown", (_event, ctx) => controller.stop(ctx));

  pi.registerCommand("terminal-logs", {
    description: "Manage captured terminal logs (usage: /terminal-logs clear)",
    handler: async (args, ctx) => {
      if (args.trim() === "clear") {
        controller.clear();
        return;
      }
      ctx.ui.notify(`${controller.getLogs().length} captured terminal log(s). Use /terminal-logs clear to remove them.`, "info");
    },
  });
}
