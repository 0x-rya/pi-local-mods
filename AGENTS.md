# AGENTS.md

## Pi local modifications workflow

This repository is the dedicated place for local Pi modifications:

`~/home/pi-local-mods`

For any Pi-related local change, do **not** edit installed package files directly, including files under:

- `~/.pi/agent/npm/node_modules/`
- `~/.nvm/versions/node/*/lib/node_modules/`

Instead:

1. Make the change in this repository.
2. Run the apply script from this repository:

   ```bash
   ./apply.sh
   ```

3. Verify the installed Pi/package files were patched as expected.
4. Restart Pi after applying.

If a live installed file was edited accidentally, move the change into this repository's patch/apply workflow and rerun `./apply.sh` so the installed copy is produced by the canonical local-mods source.

## Tmux setup workflow

The canonical tmux configuration is under `tmux/`. Do not make lasting edits directly under `~/.config/tmux`; update this repository and run:

```bash
./tmux/apply.sh
```

Use `--enable-auto-attach` when the managed zsh integration also needs to be installed. TPM checkouts and tmux-resurrect runtime snapshots are generated state and must not be committed.
