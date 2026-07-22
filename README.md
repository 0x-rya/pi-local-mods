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
