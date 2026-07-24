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

The suite applies every patch to committed fixtures (snapshots of clean Pi source) and `node --check`s the result, so it catches both applicability and JS-syntax regressions without touching the live install:

```bash
python3 -m unittest scripts.test_apply
```

CI (`.github/workflows/test.yml`) runs this on every push/PR.

## Keeping up with Pi updates

Patches are exact-string transforms, so a Pi release can shift a target and break a patch. The tooling makes drift loud, not silent:

- **`apply.sh --upgrade-pi`** reinstalls Pi, applies patches, then *automatically* runs the drift smoke test and the patch suite. If a patch no longer fits the new Pi, `apply.py` aborts with the missing needle and smoke reports drift.
- **`scripts/smoke.py`** — non-mutating drift check: patches a throwaway copy of the *currently installed* clean Pi and `node --check`s it. Run anytime: `python3 scripts/smoke.py`.
- **`tests/fixtures/VERSION`** pins the Pi version the fixtures came from. `apply.py` prints a warning when the installed Pi differs (e.g. `fixtures pinned to Pi 0.81.1 but installed Pi is 0.82.0`).
- **`scripts/refresh_fixtures.py`** — after confirming patches work on a new Pi, refresh the frozen snapshots and bump `VERSION`: `python3 scripts/refresh_fixtures.py`.

Typical upgrade flow:

```bash
./apply.sh --upgrade-pi               # upgrade + patch + auto drift/test
python3 scripts/refresh_fixtures.py   # if green, snapshot new fixtures
git commit -am "Refresh fixtures for Pi <version>"
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
