#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMUX_ROOT = ROOT / "tmux"
APPLY = TMUX_ROOT / "apply.sh"
APPLY_PY = TMUX_ROOT / "apply.py"
AUTO_ATTACH = TMUX_ROOT / "shell" / "auto-attach.zsh"
MARKER_START = "# >>> pi-local-mods tmux auto-attach >>>"
MARKER_END = "# <<< pi-local-mods tmux auto-attach <<<"


def load_apply_module():
    spec = importlib.util.spec_from_file_location("tmux_apply", APPLY_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TmuxSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = {**os.environ, "HOME": str(self.home)}
        self.mod = load_apply_module()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_apply(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(APPLY), "--skip-plugins", *args],
            cwd=ROOT,
            env=self.env,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_apply_is_idempotent_backs_up_modes_and_migrates_legacy_auto_attach(self) -> None:
        zshrc = self.home / ".zshrc"
        zshrc.write_text(f"before\n{AUTO_ATTACH.read_text()}after\n")
        zshrc.chmod(0o600)
        tmux_dir = self.home / ".config" / "tmux"
        scripts_dir = tmux_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (tmux_dir / "tmux.conf").write_text("old config\n")
        cheatsheet = scripts_dir / "cheatsheet.txt"
        shutil.copyfile(TMUX_ROOT / "scripts" / "cheatsheet.txt", cheatsheet)
        cheatsheet.chmod(0o600)

        self.run_apply("--enable-auto-attach")
        self.assertEqual((tmux_dir / "tmux.conf").read_text(), (TMUX_ROOT / "tmux.conf").read_text())
        self.assertEqual((tmux_dir / "shell" / "auto-attach.zsh").read_text(), AUTO_ATTACH.read_text())
        for source in (TMUX_ROOT / "scripts").iterdir():
            installed = scripts_dir / source.name
            self.assertEqual(installed.read_bytes(), source.read_bytes())
            expected = 0o755 if source.suffix == ".sh" else 0o644
            self.assertEqual(stat.S_IMODE(installed.stat().st_mode), expected)

        first_zshrc = zshrc.read_text()
        self.assertEqual(first_zshrc.count(MARKER_START), 1)
        self.assertIn('source "$HOME/.config/tmux/shell/auto-attach.zsh"', first_zshrc)
        self.assertNotIn(AUTO_ATTACH.read_text(), first_zshrc)
        self.assertEqual(stat.S_IMODE(zshrc.stat().st_mode), 0o600)
        self.assertEqual(len(list(self.home.glob(".zshrc.tmux-backup.*"))), 1)
        config_backups = list((tmux_dir / "backups").glob("*/tmux.conf"))
        mode_backups = list((tmux_dir / "backups").glob("*/scripts/cheatsheet.txt"))
        self.assertEqual(len(config_backups), 1)
        self.assertEqual(config_backups[0].read_text(), "old config\n")
        self.assertEqual(len(mode_backups), 1)
        self.assertEqual(stat.S_IMODE(mode_backups[0].stat().st_mode), 0o600)

        self.run_apply("--enable-auto-attach")
        self.assertEqual(zshrc.read_text(), first_zshrc)
        self.assertEqual(len(list(self.home.glob(".zshrc.tmux-backup.*"))), 1)
        self.assertEqual(len(list((tmux_dir / "backups").glob("*/tmux.conf"))), 1)

    def test_apply_refuses_symlinked_managed_file(self) -> None:
        tmux_dir = self.home / ".config" / "tmux"
        tmux_dir.mkdir(parents=True)
        external = self.home / "external.conf"
        external.write_text("do not replace\n")
        target = tmux_dir / "tmux.conf"
        target.symlink_to(external)

        result = self.run_apply(check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlinked managed path", result.stderr)
        self.assertTrue(target.is_symlink())
        self.assertEqual(external.read_text(), "do not replace\n")

    def test_modified_legacy_auto_attach_aborts_even_with_managed_block(self) -> None:
        zshrc = self.home / ".zshrc"
        managed = f"{MARKER_START}\nold source\n{MARKER_END}\n"
        original = f"{managed}# --> auto-attach to tmux on interactive shells (edited)\nmodified\n"
        zshrc.write_text(original)
        result = self.run_apply("--enable-auto-attach", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("modified legacy", result.stderr)
        self.assertFalse((self.home / ".config" / "tmux" / "tmux.conf").exists())
        self.assertEqual(zshrc.read_text(), original)

    def test_duplicate_managed_auto_attach_blocks_are_collapsed(self) -> None:
        block = f"{MARKER_START}\nold source\n{MARKER_END}\n"
        zshrc = self.home / ".zshrc"
        zshrc.write_text(f"before\n{block}middle\n{block}after\n")
        self.run_apply("--enable-auto-attach")
        text = zshrc.read_text()
        self.assertEqual(text.count(MARKER_START), 1)
        self.assertEqual(text.count(MARKER_END), 1)
        self.assertEqual(text.count('source "$HOME/.config/tmux/shell/auto-attach.zsh"'), 1)

    def create_git_repository(self, name: str = "plugin-source") -> tuple[Path, str, str]:
        repository = self.home / name
        repository.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.name", "Tmux Test"], cwd=repository, check=True)
        subprocess.run(["git", "config", "user.email", "tmux@example.invalid"], cwd=repository, check=True)
        payload = repository / "plugin.tmux"
        payload.write_text("first\n")
        subprocess.run(["git", "add", "plugin.tmux"], cwd=repository, check=True)
        subprocess.run(["git", "commit", "-qm", "first"], cwd=repository, check=True)
        first = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
        payload.write_text("second\n")
        subprocess.run(["git", "commit", "-qam", "second"], cwd=repository, check=True)
        second = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
        return repository, first, second

    def test_plugin_is_staged_pinned_and_remote_is_normalized(self) -> None:
        repository, first, _second = self.create_git_repository()
        plugin_dir = self.home / "plugins"
        plugin_dir.mkdir()
        target = plugin_dir / "demo"

        self.mod.install_plugin(plugin_dir, "demo", str(repository), first)
        self.assertEqual(self.mod.run_git(["rev-parse", "HEAD"], target), first)
        self.assertEqual(self.mod.run_git(["remote", "get-url", "origin"], target), str(repository))
        self.assertEqual(list(plugin_dir.glob(".demo.staging-*")), [])

        wrong_remote = str(self.home / "wrong-remote")
        self.mod.run_git(["remote", "set-url", "origin", wrong_remote], target)
        self.mod.install_plugin(plugin_dir, "demo", str(repository), first)
        self.assertEqual(self.mod.run_git(["remote", "get-url", "origin"], target), str(repository))

    def test_failed_plugin_staging_leaves_no_live_or_partial_checkout(self) -> None:
        repository, _first, _second = self.create_git_repository()
        plugin_dir = self.home / "plugins"
        plugin_dir.mkdir()
        with self.assertRaises(self.mod.InstallError):
            self.mod.install_plugin(plugin_dir, "broken", str(repository), "f" * 40)
        self.assertFalse((plugin_dir / "broken").exists())
        self.assertEqual(list(plugin_dir.glob(".broken.staging-*")), [])

    def test_plugin_set_stages_everything_before_publication(self) -> None:
        repository, first, second = self.create_git_repository()
        plugin_dir = self.home / "plugins"
        plugin_dir.mkdir()
        target = plugin_dir / "demo"
        subprocess.run(["git", "clone", "-q", str(repository), str(target)], check=True)

        with self.assertRaises(self.mod.InstallError):
            self.mod.install_plugin_set(
                plugin_dir,
                [("demo", str(repository), first), ("broken", str(repository), "f" * 40)],
            )
        self.assertEqual(self.mod.run_git(["rev-parse", "HEAD"], target), second)
        self.assertFalse((plugin_dir / "broken").exists())
        self.assertEqual(list(plugin_dir.glob(".*.staging-*")), [])

    def test_plugin_set_rolls_back_earlier_publications(self) -> None:
        repository_one, first_one, second_one = self.create_git_repository("source-one")
        repository_two, first_two, second_two = self.create_git_repository("source-two")
        plugin_dir = self.home / "plugins"
        plugin_dir.mkdir()
        target_one = plugin_dir / "one"
        target_two = plugin_dir / "two"
        subprocess.run(["git", "clone", "-q", str(repository_one), str(target_one)], check=True)
        subprocess.run(["git", "clone", "-q", str(repository_two), str(target_two)], check=True)

        real_replace = self.mod.os.replace
        def fail_second_publication(source, target):
            source_path = Path(source)
            target_path = Path(target)
            if source_path.name.startswith(".two.staging-") and target_path.name == "two":
                raise OSError("simulated publication failure")
            return real_replace(source, target)

        self.mod.os.replace = fail_second_publication
        try:
            with self.assertRaises(OSError):
                self.mod.install_plugin_set(
                    plugin_dir,
                    [
                        ("one", str(repository_one), first_one),
                        ("two", str(repository_two), first_two),
                    ],
                )
        finally:
            self.mod.os.replace = real_replace

        self.assertEqual(self.mod.run_git(["rev-parse", "HEAD"], target_one), second_one)
        self.assertEqual(self.mod.run_git(["rev-parse", "HEAD"], target_two), second_two)
        self.assertEqual(list(plugin_dir.glob(".*.staging-*")), [])
        self.assertEqual(list(plugin_dir.glob(".*.previous-*")), [])

    def test_shell_scripts_parse_and_removed_side_panel_scripts_stay_gone(self) -> None:
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not installed")
        scripts = [TMUX_ROOT / "apply.sh", *(TMUX_ROOT / "scripts").glob("*.sh")]
        for script in scripts:
            result = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}:\n{result.stderr}")
        self.assertFalse((TMUX_ROOT / "scripts" / "run-bonsai.sh").exists())
        self.assertFalse((TMUX_ROOT / "scripts" / "add-repo.sh").exists())

    def test_plugin_lock_uses_safe_names_repositories_and_full_commits(self) -> None:
        entries = self.mod.load_plugins()
        self.assertEqual(
            [name for name, _repository, _commit in entries],
            ["tpm", "tmux-sensible", "tmux-yank", "tmux-resurrect", "tmux-continuum"],
        )
        for _name, repository, commit in entries:
            self.assertTrue(repository.startswith("https://github.com/tmux-plugins/"))
            self.assertEqual(len(commit), 40)
            int(commit, 16)

    def test_plugin_lock_parser_rejects_traversal_and_duplicates(self) -> None:
        lock = self.home / "plugins.lock"
        original = self.mod.PLUGIN_LOCK
        self.mod.PLUGIN_LOCK = lock
        try:
            lock.write_text("../bad https://github.com/tmux-plugins/tpm.git " + "a" * 40 + "\n")
            with self.assertRaises(self.mod.InstallError):
                self.mod.load_plugins()
            lock.write_text(
                "same https://github.com/tmux-plugins/tpm.git " + "a" * 40 + "\n"
                "same https://github.com/tmux-plugins/tpm.git " + "b" * 40 + "\n"
            )
            with self.assertRaises(self.mod.InstallError):
                self.mod.load_plugins()
            lock.write_text("safe https://github.com/../repo.git " + "a" * 40 + "\n")
            with self.assertRaises(self.mod.InstallError):
                self.mod.load_plugins()
        finally:
            self.mod.PLUGIN_LOCK = original


if __name__ == "__main__":
    unittest.main()
