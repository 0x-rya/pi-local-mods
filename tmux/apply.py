#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_SOURCE = ROOT / "tmux.conf"
SCRIPTS_SOURCE = ROOT / "scripts"
AUTO_ATTACH_SOURCE = ROOT / "shell" / "auto-attach.zsh"
PLUGIN_LOCK = ROOT / "plugins.lock"
BREWFILE = ROOT / "Brewfile"
MARKER_START = "# >>> pi-local-mods tmux auto-attach >>>"
MARKER_END = "# <<< pi-local-mods tmux auto-attach <<<"
LEGACY_SENTINEL = "# --> auto-attach to tmux on interactive shells"
SAFE_PLUGIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
SAFE_PLUGIN_REPOSITORY = re.compile(
    r"https://github\.com/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?/"
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?\.git"
)


class InstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutoAttachPlan:
    path: Path
    original: str | None
    replacement: str
    mode: int


class Installer:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.tmux_dir = home / ".config" / "tmux"
        self.backup_root: Path | None = None

    def assert_regular_target(self, target: Path) -> None:
        candidate = target
        while True:
            if candidate.is_symlink():
                raise InstallError(f"Refusing to replace symlinked managed path: {candidate}")
            if candidate == self.home:
                break
            if self.home not in candidate.parents:
                raise InstallError(f"Managed path escapes HOME: {target}")
            candidate = candidate.parent
        if target.exists() and not target.is_file():
            raise InstallError(f"Managed path exists but is not a regular file: {target}")

    def managed_files(self) -> list[tuple[Path, Path, int]]:
        files = [(CONFIG_SOURCE, self.tmux_dir / "tmux.conf", 0o644)]
        files.append((AUTO_ATTACH_SOURCE, self.tmux_dir / "shell" / "auto-attach.zsh", 0o644))
        for source in sorted(SCRIPTS_SOURCE.iterdir()):
            if not source.is_file():
                raise InstallError(f"Unexpected non-file in tmux scripts source: {source}")
            mode = 0o755 if source.suffix == ".sh" else 0o644
            files.append((source, self.tmux_dir / "scripts" / source.name, mode))
        return files

    def preflight_config(self) -> None:
        for _source, target, _mode in self.managed_files():
            self.assert_regular_target(target)

    def ensure_backup_root(self) -> Path:
        if self.backup_root is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            candidate = self.tmux_dir / "backups" / stamp
            suffix = 1
            while candidate.exists():
                candidate = self.tmux_dir / "backups" / f"{stamp}-{suffix}"
                suffix += 1
            candidate.mkdir(parents=True)
            self.backup_root = candidate
        return self.backup_root

    def backup_tmux_file(self, target: Path) -> None:
        if not target.exists():
            return
        relative = target.relative_to(self.tmux_dir)
        backup = self.ensure_backup_root() / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)

    @staticmethod
    def atomic_write(target: Path, content: bytes, mode: int) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.tmp-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.chmod(mode)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def install_file(self, source: Path, target: Path, mode: int) -> None:
        self.assert_regular_target(target)
        same_content = target.exists() and filecmp.cmp(source, target, shallow=False)
        same_mode = target.exists() and stat.S_IMODE(target.stat().st_mode) == mode
        if same_content and same_mode:
            return
        self.backup_tmux_file(target)
        self.atomic_write(target, source.read_bytes(), mode)

    def install_config(self) -> None:
        for source, target, mode in self.managed_files():
            self.install_file(source, target, mode)

    def plan_auto_attach(self) -> AutoAttachPlan | None:
        zshrc = self.home / ".zshrc"
        self.assert_regular_target(zshrc)
        original = zshrc.read_text() if zshrc.exists() else None
        old_text = original or ""
        source_line = 'source "$HOME/.config/tmux/shell/auto-attach.zsh"'
        managed = f"{MARKER_START}\n{source_line}\n{MARKER_END}\n"
        marker_pattern = re.compile(
            rf"{re.escape(MARKER_START)}\n.*?{re.escape(MARKER_END)}\n?",
            re.DOTALL,
        )
        legacy = AUTO_ATTACH_SOURCE.read_text()
        managed_or_legacy = re.compile(
            rf"(?:{marker_pattern.pattern}|{re.escape(legacy)})",
            re.DOTALL,
        )
        known_blocks = list(managed_or_legacy.finditer(old_text))
        cleaned = managed_or_legacy.sub("", old_text)
        if LEGACY_SENTINEL in cleaned:
            raise InstallError(
                "Found a modified legacy tmux auto-attach block in ~/.zshrc; "
                "remove or reconcile it manually before using --enable-auto-attach"
            )
        if known_blocks:
            first_start = known_blocks[0].start()
            new_text = f"{cleaned[:first_start]}{managed}{cleaned[first_start:]}"
        else:
            separator = "" if not old_text or old_text.endswith("\n\n") else ("\n" if old_text.endswith("\n") else "\n\n")
            new_text = f"{old_text}{separator}{managed}"

        if new_text == old_text:
            return None
        mode = stat.S_IMODE(zshrc.stat().st_mode) if zshrc.exists() else 0o644
        return AutoAttachPlan(zshrc, original, new_text, mode)

    def apply_auto_attach(self, plan: AutoAttachPlan | None) -> None:
        if plan is None:
            return
        current = plan.path.read_text() if plan.path.exists() else None
        if current != plan.original:
            raise InstallError(f"Refusing to overwrite concurrently changed file: {plan.path}")
        if plan.path.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = self.home / f".zshrc.tmux-backup.{stamp}"
            suffix = 1
            while backup.exists():
                backup = self.home / f".zshrc.tmux-backup.{stamp}-{suffix}"
                suffix += 1
            shutil.copy2(plan.path, backup)
        self.atomic_write(plan.path, plan.replacement.encode(), plan.mode)


def load_plugins() -> list[tuple[str, str, str]]:
    plugins: list[tuple[str, str, str]] = []
    names: set[str] = set()
    for line_number, raw in enumerate(PLUGIN_LOCK.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 3:
            raise InstallError(f"Invalid {PLUGIN_LOCK.name} line {line_number}: {raw}")
        name, repository, commit = fields
        if not SAFE_PLUGIN_NAME.fullmatch(name) or name in {".", ".."}:
            raise InstallError(f"Unsafe plugin name on line {line_number}: {name}")
        if name in names:
            raise InstallError(f"Duplicate plugin name on line {line_number}: {name}")
        if not SAFE_PLUGIN_REPOSITORY.fullmatch(repository):
            raise InstallError(f"Unsafe plugin repository on line {line_number}: {repository}")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise InstallError(f"Invalid plugin commit on line {line_number}: {commit}")
        names.add(name)
        plugins.append((name, repository, commit))
    return plugins


def run_git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise InstallError(f"git {' '.join(args)} failed{f': {detail}' if detail else ''}")
    return result.stdout.strip()


def stage_plugin(plugin_dir: Path, name: str, repository: str, commit: str) -> Path:
    stage = Path(tempfile.mkdtemp(prefix=f".{name}.staging-", dir=plugin_dir))
    try:
        run_git(["clone", "--no-checkout", repository, str(stage)])
        run_git(["checkout", "--detach", commit], stage)
        actual = run_git(["rev-parse", "HEAD"], stage)
        if actual != commit:
            raise InstallError(f"Staged plugin {name} resolved to {actual}, expected {commit}")
        if run_git(["status", "--porcelain"], stage):
            raise InstallError(f"Staged plugin checkout is unexpectedly dirty: {name}")
        return stage
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


@dataclass
class PluginPlan:
    name: str
    repository: str
    commit: str
    target: Path
    stage: Path | None
    previous: Path | None = None
    published: bool = False


def prepare_plugin(plugin_dir: Path, name: str, repository: str, commit: str) -> PluginPlan:
    target = plugin_dir / name
    if target.is_symlink():
        raise InstallError(f"Refusing to replace symlinked plugin path: {target}")
    if target.exists():
        if not target.is_dir() or not (target / ".git").exists():
            raise InstallError(f"Plugin path exists but is not a git checkout: {target}")
        if run_git(["status", "--porcelain"], target):
            raise InstallError(f"Refusing to update dirty plugin checkout: {target}")
        current = run_git(["rev-parse", "HEAD"], target)
        if current == commit:
            remote = run_git(["remote", "get-url", "origin"], target)
            if remote == repository:
                return PluginPlan(name, repository, commit, target, None)

    print(f"Staging {name} at {commit[:8]}...")
    stage = stage_plugin(plugin_dir, name, repository, commit)
    return PluginPlan(name, repository, commit, target, stage)


def rollback_published_plugins(plans: list[PluginPlan]) -> None:
    errors: list[str] = []
    for plan in reversed(plans):
        if not plan.published:
            continue
        try:
            if plan.previous is None:
                shutil.rmtree(plan.target)
            else:
                failed = plan.target.with_name(f".{plan.target.name}.failed-{uuid.uuid4().hex}")
                os.replace(plan.target, failed)
                os.replace(plan.previous, plan.target)
                shutil.rmtree(failed, ignore_errors=True)
            plan.published = False
        except OSError as error:
            errors.append(f"{plan.name}: {error}")
    if errors:
        raise InstallError(f"Plugin rollback failed: {'; '.join(errors)}")


def install_plugin_set(plugin_dir: Path, plugins: list[tuple[str, str, str]]) -> None:
    plans: list[PluginPlan] = []
    try:
        for name, repository, commit in plugins:
            plans.append(prepare_plugin(plugin_dir, name, repository, commit))
    except BaseException:
        for plan in plans:
            if plan.stage is not None:
                shutil.rmtree(plan.stage, ignore_errors=True)
        raise

    try:
        for plan in plans:
            if plan.stage is None:
                continue
            if plan.target.exists():
                plan.previous = plan.target.with_name(f".{plan.target.name}.previous-{uuid.uuid4().hex}")
                os.replace(plan.target, plan.previous)
            try:
                os.replace(plan.stage, plan.target)
            except BaseException:
                if plan.previous is not None:
                    os.replace(plan.previous, plan.target)
                    plan.previous = None
                raise
            plan.published = True
            actual = run_git(["rev-parse", "HEAD"], plan.target)
            if actual != plan.commit:
                raise InstallError(f"Published plugin {plan.name} resolved to {actual}, expected {plan.commit}")
            if run_git(["status", "--porcelain"], plan.target):
                raise InstallError(f"Published plugin checkout is unexpectedly dirty: {plan.name}")

        for plan in plans:
            remote = run_git(["remote", "get-url", "origin"], plan.target)
            if remote != plan.repository:
                raise InstallError(
                    f"Published plugin {plan.name} has remote {remote}, expected {plan.repository}"
                )
    except BaseException:
        rollback_published_plugins(plans)
        raise
    finally:
        for plan in plans:
            if plan.stage is not None and plan.stage.exists():
                shutil.rmtree(plan.stage, ignore_errors=True)

    for plan in plans:
        if plan.previous is not None:
            shutil.rmtree(plan.previous, ignore_errors=True)


def install_plugin(plugin_dir: Path, name: str, repository: str, commit: str) -> None:
    install_plugin_set(plugin_dir, [(name, repository, commit)])


def install_plugins(tmux_dir: Path, plugins: list[tuple[str, str, str]]) -> None:
    if shutil.which("git") is None:
        raise InstallError("Missing required command: git")
    plugin_dir = tmux_dir / "plugins"
    if plugin_dir.is_symlink():
        raise InstallError(f"Refusing to use symlinked plugin directory: {plugin_dir}")
    if plugin_dir.exists() and not plugin_dir.is_dir():
        raise InstallError(f"Plugin path exists but is not a directory: {plugin_dir}")
    plugin_dir.mkdir(parents=True, exist_ok=True)
    install_plugin_set(plugin_dir, plugins)


def install_dependencies() -> None:
    brew = shutil.which("brew")
    if brew is None:
        raise InstallError("--install-deps requires Homebrew (brew)")
    result = subprocess.run([brew, "bundle", f"--file={BREWFILE}"])
    if result.returncode != 0:
        raise InstallError(f"Homebrew dependency installation failed with exit code {result.returncode}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install the repository's tmux setup")
    parser.add_argument("--install-deps", action="store_true", help="install Homebrew dependencies from Brewfile")
    parser.add_argument("--enable-auto-attach", action="store_true", help="source the managed auto-attach fragment from ~/.zshrc")
    parser.add_argument("--skip-plugins", action="store_true", help="do not clone or pin TPM plugins")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    home_value = os.environ.get("HOME")
    if not home_value:
        raise InstallError("HOME is not set")
    home = Path(home_value).expanduser().resolve()
    installer = Installer(home)

    installer.preflight_config()
    auto_attach_plan = installer.plan_auto_attach() if args.enable_auto_attach else None
    plugins = [] if args.skip_plugins else load_plugins()

    if args.install_deps:
        install_dependencies()
    if not args.skip_plugins:
        install_plugins(installer.tmux_dir, plugins)
    installer.install_config()
    installer.apply_auto_attach(auto_attach_plan)

    print(f"Installed tmux setup in {installer.tmux_dir}")
    if installer.backup_root:
        print(f"Backups: {installer.backup_root}")
    if args.enable_auto_attach:
        print("Enabled tmux auto-attach in ~/.zshrc; start a new shell to use it.")


if __name__ == "__main__":
    try:
        main()
    except InstallError as error:
        raise SystemExit(str(error)) from None
