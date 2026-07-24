import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";
import { execFile } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";


type WindowLimit = {
  remaining?: string;
  usedPercent?: number;
  reset?: string;
  windowMinutes?: number;
  updated: number;
  source?: string;
};

type ProviderState = {
  fiveHour?: WindowLimit;
  weekly?: WindowLimit;
  error?: string;
  note?: string;
  updated?: number;
};

type LeanCtxState = {
  available: boolean;
  active: boolean;
  bridgeOff: boolean;
  tokensSaved?: string;
  compression?: string;
  usdSaved?: string;
  error?: string;
  updated: number;
};

const states = new Map<string, ProviderState>();
let leanCtx: LeanCtxState = { available: false, active: false, bridgeOff: false, updated: 0 };
const statePath = join(process.env.HOME ?? ".", ".pi/agent/quota-dashboard-state.json");
const authPath = join(process.env.HOME ?? ".", ".pi/agent/auth.json");
const leanCtxBin = process.env.LEAN_CTX_BIN || "/opt/homebrew/bin/lean-ctx";
// Z.ai exposes a real quota endpoint (https://github.com/rygel/AIUsageTracker).
// Raw API key in the Authorization header (no Bearer). Used to show live remaining
// usage instead of only learning limits from 429 error bodies.
const zaiQuotaEndpoint = "https://api.z.ai/api/monitor/usage/quota/limit";
const aliases: Record<string, string> = {
  "openai-codex": "Codex",
  openai: "OpenAI",
  zai: "Zai",
  google: "Gemini",
  anthropic: "Anthropic",
};

function providerName(provider: string) {
  return aliases[provider] ?? provider;
}

function loadState() {
  try {
    const raw = JSON.parse(readFileSync(statePath, "utf8")) as Record<string, ProviderState>;
    states.clear();
    for (const [provider, state] of Object.entries(raw)) states.set(provider, state);
  } catch {
    // No previous quota state yet, or unreadable cache. Ignore.
  }
}

function saveState() {
  try {
    mkdirSync(dirname(statePath), { recursive: true });
    writeFileSync(statePath, JSON.stringify(Object.fromEntries(states), null, 2));
  } catch {
    // UI data only; never break pi if persistence fails.
  }
}

function lowerHeaders(headers: Record<string, string>) {
  return Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), String(v)]));
}

function findHeader(headers: Record<string, string>, names: string[]) {
  const h = lowerHeaders(headers);
  for (const name of names) {
    const value = h[name.toLowerCase()];
    if (value !== undefined && value !== "") return value;
  }
  return undefined;
}

function parseNumber(value?: string) {
  if (value === undefined || value === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function formatDuration(ms: number) {
  if (ms <= 0) return "now";
  const days = Math.floor(ms / 86_400_000);
  const hours = Math.floor((ms % 86_400_000) / 3_600_000);
  const mins = Math.floor((ms % 3_600_000) / 60_000);
  if (days > 0) return `in ${days}d ${hours}h`;
  if (hours > 0) return `in ${hours}h ${mins}m`;
  return `in ${mins}m`;
}

function formatReset(value?: string) {
  if (!value) return "";
  const n = Number(value);
  if (Number.isFinite(n)) {
    const ms = n < 10_000_000_000 ? n * 1000 : n;
    return formatDuration(ms - Date.now());
  }
  const parsed = Date.parse(value.replace(" ", "T"));
  if (!Number.isNaN(parsed)) return formatDuration(parsed - Date.now());
  return value;
}

function remainingPercent(limit?: WindowLimit) {
  if (!limit) return undefined;
  if (limit.usedPercent !== undefined) return Math.max(0, 100 - limit.usedPercent);
  const match = limit.remaining?.match(/(\d+(?:\.\d+)?)%/);
  return match ? Number(match[1]) : undefined;
}

function colorByRemaining(theme: any, text: string, limit?: WindowLimit) {
  const percent = remainingPercent(limit);
  if (percent === undefined) return theme.fg("dim", text);
  if (percent <= 15) return theme.fg("error", text);
  if (percent <= 35) return theme.fg("warning", text);
  return theme.fg("success", text);
}

function formatWindow(theme: any, label: string, limit?: WindowLimit) {
  const labelText = theme.fg("muted", `${label}:`);
  if (!limit) return `${labelText} ${theme.fg("dim", "—")}`;
  const reset = formatReset(limit.reset);
  const value = limit.remaining ?? (limit.usedPercent !== undefined ? `${100 - limit.usedPercent}% left` : "?");
  return `${labelText} ${colorByRemaining(theme, value, limit)}${reset ? ` ${theme.fg("dim", `(${reset})`)}` : ""}`;
}

function bucketFromCodexHeaders(headers: Record<string, string>, stem: string, source: string): WindowLimit | undefined {
  const windowMinutes = parseNumber(findHeader(headers, [`${stem}-window-minutes`]));
  if (!windowMinutes || windowMinutes <= 0) return undefined;

  const usedPercent = parseNumber(findHeader(headers, [`${stem}-used-percent`]));
  const resetAt = findHeader(headers, [`${stem}-reset-at`]);
  const resetAfter = parseNumber(findHeader(headers, [`${stem}-reset-after-seconds`]));
  const reset = resetAt || (resetAfter !== undefined ? String(Date.now() + resetAfter * 1000) : undefined);
  const remaining = usedPercent !== undefined ? `${Math.max(0, 100 - usedPercent)}% left` : undefined;

  return { remaining, usedPercent, reset, windowMinutes, updated: Date.now(), source };
}

function assignCodexBucket(state: ProviderState, bucket?: WindowLimit) {
  if (!bucket?.windowMinutes) return;
  // Codex reports windows by minutes. Weekly is 10080. A 5h bucket, when present,
  // should be 300; tolerate nearby values in case the backend changes slightly.
  if (bucket.windowMinutes >= 9_000) state.weekly = bucket;
  else if (bucket.windowMinutes >= 240 && bucket.windowMinutes <= 360) state.fiveHour = bucket;
}

function parseCodexHeaders(headers: Record<string, string>, state: ProviderState) {
  assignCodexBucket(state, bucketFromCodexHeaders(headers, "x-codex-primary", "codex"));
  assignCodexBucket(state, bucketFromCodexHeaders(headers, "x-codex-secondary", "codex"));

  const spark = bucketFromCodexHeaders(headers, "x-codex-bengalfox-primary", "codex-spark");
  const sparkName = findHeader(headers, ["x-codex-bengalfox-limit-name"]);
  if (spark && sparkName) {
    const remaining = spark.remaining ?? "?";
    state.note = `${sparkName}: ${remaining}`;
  }
}

function parseGenericRateLimitHeaders(headers: Record<string, string>, kind: "fiveHour" | "weekly") {
  const suffix = kind === "fiveHour" ? ["5h", "5-hour", "5_hour"] : ["week", "weekly", "7d"];
  const remaining = findHeader(headers, suffix.flatMap((s) => [
    `x-ratelimit-remaining-${s}`,
    `x-ratelimit-${s}-remaining`,
    `ratelimit-remaining-${s}`,
    `x-${s}-remaining`,
  ]));
  const reset = findHeader(headers, suffix.flatMap((s) => [
    `x-ratelimit-reset-${s}`,
    `x-ratelimit-${s}-reset`,
    `ratelimit-reset-${s}`,
    `x-${s}-reset`,
  ]));
  if (!remaining && !reset) return undefined;
  return { remaining, reset, updated: Date.now() };
}

function parseZaiLimitMessage(text: string, state: ProviderState) {
  const match = text.match(/Usage limit reached for\s+(\d+)\s+hour.*?reset at\s+([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{2}:[0-9]{2}:[0-9]{2})/i);
  if (!match) return false;
  const hours = Number(match[1]);
  const reset = match[2];
  const limit: WindowLimit = { remaining: "0% left", reset, windowMinutes: hours * 60, updated: Date.now(), source: "zai-error" };
  if (hours === 5) state.fiveHour = limit;
  else if (hours * 60 >= 9_000) state.weekly = limit;
  state.error = "rate limited";
  state.updated = Date.now();
  return true;
}

function readZaiApiKey(): string | undefined {
  try {
    const auth = JSON.parse(readFileSync(authPath, "utf8")) as Record<string, { key?: string }>;
    return auth.zai?.key;
  } catch {
    return undefined;
  }
}

// Only surface providers the user has actually authenticated. Keeps the dashboard
// free of providers (e.g. Gemini) the user removed from their config. Ordered
// by a stable preference, with any unknown extras appended.
function authenticatedProviders(): string[] {
  let keys = new Set<string>();
  try {
    const auth = JSON.parse(readFileSync(authPath, "utf8")) as Record<string, unknown>;
    keys = new Set(Object.keys(auth));
  } catch {
    // Fall back to whatever quota state we have on disk.
  }
  if (keys.size === 0) keys = new Set(states.keys());
  const preferred = ["openai-codex", "openai", "zai", "google", "anthropic"];
  const ordered = preferred.filter((p) => keys.has(p));
  for (const key of keys) if (!preferred.includes(key)) ordered.push(key);
  return ordered;
}

// Map a z.ai quota/limit item onto our WindowLimit. Note: z.ai names the total
// field "usage" (confusingly), "percentage" is percent USED, and nextResetTime
// is epoch ms when > 1e10 else epoch seconds.
function zaiBucketFromLimit(item: any, source: string): WindowLimit | undefined {
  if (!item || item.type === undefined) return undefined;
  const usedPercent = typeof item.percentage === "number" ? item.percentage : undefined;
  const total = typeof item.usage === "number" ? item.usage : undefined;
  const remainingRaw = typeof item.remaining === "number" ? item.remaining : undefined;
  const resetMs = typeof item.nextResetTime === "number"
    ? (item.nextResetTime > 10_000_000_000 ? item.nextResetTime : item.nextResetTime * 1000)
    : undefined;
  let remainingPct: number | undefined;
  if (usedPercent !== undefined) remainingPct = Math.max(0, 100 - usedPercent);
  else if (total && total > 0 && remainingRaw !== undefined) remainingPct = (remainingRaw / total) * 100;
  const remaining = remainingPct !== undefined ? `${remainingPct.toFixed(0)}% left` : undefined;
  // unit 3 = hours, unit 5 = months (z.ai convention).
  const windowMinutes = item.unit === 3 && typeof item.number === "number" ? item.number * 60
    : item.unit === 5 && typeof item.number === "number" ? item.number * 30 * 24 * 60
    : undefined;
  return {
    remaining,
    usedPercent,
    reset: resetMs !== undefined ? String(resetMs) : undefined,
    windowMinutes,
    updated: Date.now(),
    source,
  };
}

async function fetchZaiQuota(): Promise<boolean> {
  const key = readZaiApiKey();
  if (!key) return false;
  let body: any;
  try {
    const resp = await fetch(zaiQuotaEndpoint, { headers: { Authorization: key, "Accept-Language": "en-US,en" } });
    if (!resp.ok) return false;
    body = await resp.json();
  } catch {
    return false;
  }
  const limits: any[] | undefined = body?.data?.limits;
  if (!Array.isArray(limits) || limits.length === 0) return false;
  const tokens = limits.find((l) => String(l?.type).toUpperCase() === "TOKENS_LIMIT");
  const time = limits.find((l) => String(l?.type).toUpperCase() === "TIME_LIMIT");
  const state: ProviderState = states.get("zai") ?? {};
  const fiveHour = zaiBucketFromLimit(tokens, "zai-api");
  const weekly = zaiBucketFromLimit(time, "zai-api");
  if (fiveHour) state.fiveHour = fiveHour;
  if (weekly) state.weekly = weekly;
  if (fiveHour || weekly) state.error = undefined;
  state.updated = Date.now();
  states.set("zai", state);
  saveState();
  return true;
}

function stripAnsi(text: string) {
  return text.replace(/\x1b\[[0-9;]*m/g, "");
}

function runLeanCtx(args: string[]): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(leanCtxBin, args, { timeout: 8_000, maxBuffer: 1024 * 1024 }, (error, stdout, stderr) => {
      const output = stripAnsi(`${stdout || ""}\n${stderr || ""}`.trim());
      if (error) reject(new Error(output || error.message));
      else resolve(output);
    });
  });
}

function parseLeanGain(output: string) {
  const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].includes("tokens saved")) continue;
    // The values row sits just above the "tokens saved" label, with a bar row
    // (━━━) drawn between them — so lines[i-1] is the bars, not the numbers.
    // Scan upward for the first row carrying the "<tokens> <pct%> [commands]
    // $<usd>" triple, which survives minor box-layout changes.
    for (let j = i - 1; j >= Math.max(0, i - 4); j--) {
      const values = lines[j].match(/([0-9][0-9.,kKmM]*)\s+([0-9]+(?:\.[0-9]+)?%)\s+(?:[0-9][0-9.,kKmM]*\s+)?(\$[0-9.]+)/);
      if (values) return { tokensSaved: values[1], compression: values[2], usdSaved: values[3] };
    }
  }
  return {};
}

async function refreshLeanCtx() {
  try {
    const [statusOutput, gainOutput] = await Promise.all([runLeanCtx(["status"]), runLeanCtx(["gain", "--deep"])]);
    const gain = parseLeanGain(gainOutput);
    leanCtx = {
      available: true,
      active: /shadow_mode:\s*active/i.test(statusOutput) || /Daemon:\s*running/i.test(gainOutput),
      bridgeOff: /Bridge:\s*OFF/i.test(gainOutput),
      ...gain,
      updated: Date.now(),
    };
  } catch (error) {
    leanCtx = {
      available: false,
      active: false,
      bridgeOff: false,
      error: error instanceof Error && error.message.includes("ENOENT") ? "not found" : "error",
      updated: Date.now(),
    };
  }
}

function formatLeanCtx(theme: any) {
  if (!leanCtx.available) return `${theme.fg("error", "lean-ctx off")}${leanCtx.error ? theme.fg("dim", ` (${leanCtx.error})`) : ""}`;
  const status = leanCtx.active ? theme.fg("success", "on") : theme.fg("warning", "off");
  const bridge = leanCtx.bridgeOff ? theme.fg("warning", "/bridge off") : "";
  // Only print the savings clause when values were actually parsed, so a future
  // lean-ctx box-layout change degrades to "lean-ctx on" instead of "saved ? tok ? $?".
  const savings = leanCtx.tokensSaved
    ? theme.fg("dim", `saved ${leanCtx.tokensSaved} tok ${leanCtx.compression ?? "?"} ${leanCtx.usdSaved ?? "$?"}`)
    : "";
  return `${theme.fg("accent", "lean-ctx")} ${status}${bridge}${savings ? ` ${savings}` : ""}`;
}

function render(ctx: ExtensionContext, pi?: ExtensionAPI) {
  if (!ctx.hasUI) return;
  const theme = (ctx.ui as any).theme;
  const active = ctx.model ? `${providerName(ctx.model.provider)}/${ctx.model.id}` : "none";
  const providers = authenticatedProviders();
  const parts = providers.map((provider) => {
    const state = states.get(provider);
    const providerLabel = theme.fg("accent", providerName(provider));
    const error = state?.error ? ` ${theme.fg("error", `· ${state.error}`)}` : "";
    const note = state?.note ? ` ${theme.fg("warning", `· ${state.note}`)}` : "";
    return `${providerLabel} ${formatWindow(theme, "5h", state?.fiveHour)} ${theme.fg("dim", "·")} ${formatWindow(theme, "wk", state?.weekly)}${error}${note}`;
  });
  const age = Math.max(...[...states.values()].map((s) => s.updated ?? 0), 0);
  const freshness = age ? theme.fg("dim", ` · updated ${Math.max(0, Math.floor((Date.now() - age) / 1000))}s ago`) : theme.fg("dim", " · waiting for provider response");
  const thinking = pi ? ` ${theme.fg("dim", "·")} ${theme.fg("muted", "thinking")} ${theme.fg("accent", pi.getThinkingLevel())}` : "";
  ctx.ui.setWidget("quota-dashboard", [
    `${theme.fg("muted", "Limits")}  ${theme.fg("dim", "│")} ${parts.join(`  ${theme.fg("dim", "│")}  `)}`,
    `${theme.fg("muted", "Active")}  ${theme.fg("dim", "│")} ${theme.fg("accent", active)}${thinking}${freshness} ${theme.fg("dim", "│")} ${formatLeanCtx(theme)}`,
  ], { placement: "belowEditor" });
}

export default function (pi: ExtensionAPI) {
  let refreshTimer: ReturnType<typeof setInterval> | undefined;
  let sessionGeneration = 0;

  const showHotkeys = async () => {
    pi.sendUserMessage("/hotkeys");
  };

  // "?" is Shift+"/", so pressing Ctrl+? is physically Ctrl+Shift+"/". A keyId
  // of "ctrl+?" parses to modifier=ctrl only (the Shift is dropped) and never
  // matches the real keypress. Under Kitty keyboard / modifyOtherKeys, Ctrl+?
  // arrives with shift+ctrl set, reported either as the shifted codepoint "?"
  // (63) or the base key "/" (47). Bind the shift-inclusive forms that actually
  // match, plus "ctrl+/" as the unshifted alias.
  for (const shortcut of ["ctrl+shift+?", "ctrl+shift+/", "ctrl+/", "ctrl+?"]) {
    pi.registerShortcut(shortcut, {
      description: "Show keyboard shortcuts",
      handler: showHotkeys,
    });
  }

  const thinkingLevels = ["off", "minimal", "low", "medium", "high", "xhigh", "max"] as const;
  const adjustThinking = (delta: -1 | 1) => {
    const current = pi.getThinkingLevel();
    const index = Math.max(0, thinkingLevels.indexOf(current as (typeof thinkingLevels)[number]));
    const nextIndex = Math.max(0, Math.min(thinkingLevels.length - 1, index + delta));
    pi.setThinkingLevel(thinkingLevels[nextIndex]);
  };

  pi.registerShortcut("alt+,", {
    description: "Decrease thinking effort",
    handler: async () => adjustThinking(-1),
  });

  pi.registerShortcut("alt+.", {
    description: "Increase thinking effort",
    handler: async () => adjustThinking(1),
  });

  let leanRefreshInFlight = false;
  const refreshLeanAndRender = async (ctx: ExtensionContext, generation = sessionGeneration) => {
    if (generation !== sessionGeneration) return;
    if (leanRefreshInFlight) return;
    leanRefreshInFlight = true;
    try {
      await refreshLeanCtx();
    } finally {
      leanRefreshInFlight = false;
      if (generation === sessionGeneration) render(ctx, pi);
    }
  };

  pi.on("session_start", (_event, ctx) => {
    const generation = ++sessionGeneration;
    loadState();
    ctx.ui.setFooter(() => ({
      invalidate() {},
      render() { return []; },
    }));
    render(ctx, pi);
    void refreshLeanAndRender(ctx, generation);
    void fetchZaiQuota().then((ok) => { if (ok && generation === sessionGeneration) render(ctx, pi); });
    if (refreshTimer) clearInterval(refreshTimer);
    // Live UI: recompute reset countdowns/staleness and refresh lean-ctx stats.
    // zai quota is pulled from its API on a slower cadence (every ~3 min) to
    // avoid hammering the endpoint; lean-ctx + countdowns refresh every 15s.
    let zaiTick = 0;
    refreshTimer = setInterval(() => {
      if (generation !== sessionGeneration) return;
      render(ctx, pi);
      void refreshLeanAndRender(ctx, generation);
      if (++zaiTick % 12 === 0) void fetchZaiQuota().then((ok) => { if (ok && generation === sessionGeneration) render(ctx, pi); });
    }, 15_000);
  });

  pi.on("session_shutdown", (_event, ctx) => {
    sessionGeneration++;
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = undefined;
    ctx.ui.setFooter(undefined);
  });

  pi.on("model_select", (_event, ctx) => {
    render(ctx, pi);
  });

  pi.on("thinking_level_select", (_event, ctx) => {
    render(ctx, pi);
  });

  pi.on("after_provider_response", (event, ctx) => {
    const provider = ctx.model?.provider;
    if (!provider) return;

    const headers = lowerHeaders(event.headers ?? {});
    const state = states.get(provider) ?? {};

    if (provider === "openai-codex") parseCodexHeaders(headers, state);
    else {
      state.fiveHour = parseGenericRateLimitHeaders(headers, "fiveHour") ?? state.fiveHour;
      state.weekly = parseGenericRateLimitHeaders(headers, "weekly") ?? state.weekly;
    }

    state.updated = Date.now();
    if (event.status === 429) state.error = "rate limited";
    else if (event.status >= 400) state.error = `HTTP ${event.status}`;
    else {
      // Success: clear any stale error state. Zai exposes no positive limit
      // headers — it only announces resets inside 429 bodies — so a prior
      // "0% left / rate limited" snapshot taken from an old error must be
      // dropped here, otherwise the dashboard freezes at "0% left" forever
      // even while requests succeed. Non-zai providers keep their real data.
      state.error = undefined;
      if (provider === "zai") {
        if (state.fiveHour?.source === "zai-error") state.fiveHour = undefined;
        if (state.weekly?.source === "zai-error") state.weekly = undefined;
      }
    }

    states.set(provider, state);
    saveState();
    render(ctx, pi);
  });

  pi.on("message_end", (event, ctx) => {
    const raw = event.message as any;
    const provider = raw.provider as string | undefined;
    if (provider !== "zai") return;
    const text = JSON.stringify(raw);
    const state = states.get("zai") ?? {};
    if (parseZaiLimitMessage(text, state)) {
      states.set("zai", state);
      saveState();
      render(ctx, pi);
    }
  });

  pi.on("turn_end", (_event, ctx) => {
    void refreshLeanAndRender(ctx);
    // A turn just consumed zai quota; refresh live remaining usage.
    void fetchZaiQuota().then((ok) => { if (ok) render(ctx, pi); });
  });

  pi.registerCommand("limits", {
    description: "Refresh and display provider quota information",
    handler: async (_args, ctx) => {
      await refreshLeanAndRender(ctx);
      ctx.ui.notify("Quota dashboard refreshed. Codex updates from x-codex-* headers; Zai only exposes resets on usage-limit errors.", "info");
    },
  });
}
