# pi-local-mods

Reproducible local setup for the Pi coding agent and tmux.

The Pi changes are intentionally **not** implemented as a Pi extension because the useful parts patch Pi internals that are not currently exposed to extensions:

- transcript mouse/trackpad scrolling
- app-owned transcript selection + copy
- scroll anchoring while streaming / expanding tool output
- custom `codex-dark` theme

## Apply Pi patches

```bash
./apply.sh
```

`apply.sh` checks for `python3` and `node`. It also checks for `npm` when using the global npm Pi install path. If the global `@earendil-works/pi-coding-agent` package is missing, it installs it, then applies the local patches. If `PI_CODING_AGENT_DIR` is set, that directory is used instead of installing/patching the global npm package.

To explicitly update Pi before patching:

```bash
./apply.sh --upgrade-pi
```

To install a specific Pi version during bootstrap/upgrade:

```bash
PI_VERSION=0.81.1 ./apply.sh --upgrade-pi
```

To patch only without bootstrapping packages:

```bash
./apply.sh --no-bootstrap
```

Restart Pi after applying.

## Test

The suite applies every patch to committed fixtures (snapshots of clean Pi source) and `node --check`s the result, so it catches both applicability and JS-syntax regressions without touching the live install:

```bash
python3 -m unittest scripts.test_apply scripts.test_tmux
```

CI (`.github/workflows/test.yml`) runs this on every push/PR. A second `drift` job installs the **latest published Pi** and smoke-tests the patches against it on every push/PR, so an upstream Pi release that breaks a patch fails the build and must be fixed before merging.

## Keeping up with `pi update`

Patches are exact-string transforms, so a Pi release can shift a target and break a patch. The tooling makes drift loud, not silent.

### Auto re-apply after `pi update` (recommended)

`apply.sh` automatically installs a `pi update` hook into `~/.zshrc` (backing it up to `~/.zshrc.pi-local-mods.bak` the first time). It's idempotent, so re-running `apply.sh` won't duplicate the block.

Once sourced, every successful `pi update` automatically re-applies the patches and runs the drift smoke test + patch suite: update Pi → re-apply patches → smoke-test → run the suite. If a patch drifted on the new Pi, `apply.py` aborts and the hook reports it.

The hook lives in your shell profile, not in Pi's files, so it survives every update — unlike patching Pi's own update routine, which `pi update` would wipe (chicken-and-egg). It overrides `pi` as a shell function and calls the real binary via `command pi`, so it only acts on a successful `update`.

> Using bash instead of zsh? Run `python3 scripts/install_hook.py ~/.bashrc` (the default targets `~/.zshrc`).

### Manual drift checks (anytime)

- `python3 scripts/smoke.py` — non-mutating: patches a throwaway copy of the installed Pi and `node --check`s it.
- `tests/fixtures/VERSION` pins the Pi version the fixtures came from; `apply.py` warns when the installed Pi differs.
- `python3 scripts/refresh_fixtures.py` — after confirming patches work on a new Pi, refresh the snapshots and bump `VERSION`, then commit.

> `./apply.sh --upgrade-pi` still exists as a one-shot "install/upgrade Pi + patch" convenience (e.g. a fresh machine), but day-to-day updates go through `pi update` + the hook above.

## Tmux setup

The canonical tmux configuration lives in [`tmux/`](tmux/):

- `tmux.conf` and the scripts/cheatsheet it invokes
- the zsh auto-attach/workspace fragment
- a Homebrew dependency manifest
- exact commits for TPM and all configured plugins
- an idempotent installer with backups

Apply the configuration and pinned plugins:

```bash
./tmux/apply.sh
```

On a fresh Mac, install dependencies and enable automatic tmux attachment in zsh too:

```bash
./tmux/apply.sh --install-deps --enable-auto-attach
```

Useful options:

- `--install-deps` — run `brew bundle` for tmux, cbonsai, and git
- `--enable-auto-attach` — replace the legacy inline block, if present, with a managed `~/.zshrc` source block
- `--skip-plugins` — install only config/scripts (used by offline tests)

Changed live files are backed up under `~/.config/tmux/backups/`; a changed `.zshrc` is backed up beside the original. Managed-file symlinks are refused rather than replaced. Plugins are staged and commit-verified before publication. The installer intentionally does not delete unlisted helper/plugin directories, which may be user-owned; remove obsolete entries manually.

The repository does not commit or copy TPM checkouts, tmux-resurrect snapshots, pane contents, or other runtime state.

The setup targets macOS (`pbcopy`) and uses Ghostty's Kitty/extended-key support. To preserve the configured Shift+Enter behavior, keep this in Ghostty's config:

```ini
keybind = shift+enter=text:\n
```

After applying, either reload with `prefix + r` or restart tmux. Start a new shell after enabling auto-attach.

## Selection UX

- Wheel/trackpad scroll: scrolls transcript
- Drag: selects transcript text inside Pi
- `Ctrl+X`: copies Pi selection if one exists, otherwise Pi's normal copy action runs
- `Esc`: clears Pi selection
- Auto-copy on mouse release is **off by default**
- Optional auto-copy:

```bash
PI_SELECTION_AUTO_COPY=1 pi
```

## Notes

This patches installed package files under your current global npm Pi install. A future Pi upgrade may overwrite these changes; rerun `./apply.sh` after upgrading.
