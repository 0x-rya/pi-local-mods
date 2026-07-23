# pi-local-mods

Personal local patches for the globally installed Pi coding agent.

These are intentionally **not** implemented as a Pi extension because the useful parts patch Pi internals that are not currently exposed to extensions:

- transcript mouse/trackpad scrolling
- app-owned transcript selection + copy
- scroll anchoring while streaming / expanding tool output
- custom `codex-dark` theme

## Apply

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

The test suite applies patches to committed fixtures, not to the live Pi install:

```bash
python3 -m unittest scripts/test_apply.py
```

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
