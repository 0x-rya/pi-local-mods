# AGENTS.md

## Pi local modifications workflow

This repository is the dedicated place for local Pi modifications:

`/Users/atan2/home/pi-local-mods`

For any Pi-related local change, do **not** edit installed package files directly, including files under:

- `/Users/atan2/.pi/agent/npm/node_modules/`
- `/Users/atan2/.nvm/versions/node/*/lib/node_modules/`

Instead:

1. Make the change in this repository.
2. Run the apply script from this repository:

   ```bash
   ./apply.sh
   ```

3. Verify the installed Pi/package files were patched as expected.
4. Restart Pi after applying.

If a live installed file was edited accidentally, move the change into this repository's patch/apply workflow and rerun `./apply.sh` so the installed copy is produced by the canonical local-mods source.
