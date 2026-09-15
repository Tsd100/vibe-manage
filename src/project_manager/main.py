from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path

from .config import AppConfig, DataDirectoryError
from .scanner import discover_repositories_many
from .settings import settings_from_mapping
from .storage import JsonStore


WINDOWS_APP_USER_MODEL_ID = "VibeManage.ProjectManager"


def set_windows_app_user_model_id() -> bool:
    """Give Windows taskbar grouping a stable identity for this application."""

    if os.name != "nt":
        return False
    try:
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(WINDOWS_APP_USER_MODEL_ID)
        )
    except (AttributeError, OSError, TypeError):
        return False
    return result == 0


def enable_windows_dpi_awareness() -> bool:
    """Enable per-monitor DPI awareness before Tk creates any windows."""
    if os.name != "nt":
        return False
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return True
    except (AttributeError, OSError, OverflowError):
        pass
    try:
        return ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
    except (AttributeError, OSError):
        return False


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Windows 项目管理看板")
    parser.add_argument("--repo-root", type=Path, help="Git 项目根目录")
    parser.add_argument("--data-dir", type=Path, help="运行数据目录")
    parser.add_argument("--self-check", action="store_true", help="只检查配置和目录，不打开窗口")
    parser.add_argument("--no-tray", action="store_true", help="开发测试时禁用托盘")
    return parser


def _config_from_args(args: argparse.Namespace) -> AppConfig:
    base = AppConfig.from_environment()
    return AppConfig(repo_root=args.repo_root or base.repo_root, data_dir=args.data_dir or base.data_dir)


def self_check(config: AppConfig) -> int:
    try:
        config.ensure_data_dirs()
    except DataDirectoryError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "data_dir": str(config.data_dir)}, ensure_ascii=False))
        return 2
    registry = JsonStore(config.data_dir / "inventory" / "projects-registry.json").load(default={"projects": []}) or {}
    saved_settings = JsonStore(config.data_dir / "settings.json").load(default={}) or {}
    settings = settings_from_mapping(saved_settings, fallback_repo_roots=(str(config.repo_root),))
    roots = [Path(value) for value in settings.repo_roots]
    print(json.dumps({
        "ok": True,
        "repo_root": str(config.repo_root),
        "repo_roots": list(settings.repo_roots),
        "data_dir": str(config.data_dir),
        "repository_count": len(discover_repositories_many(roots)),
        "registry_count": len(registry.get("projects", [])),
    }, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = _config_from_args(args)
    if args.self_check:
        return self_check(config)
    import tkinter as tk
    from tkinter import messagebox

    from .ui import ProjectManagerApp

    enable_windows_dpi_awareness()
    set_windows_app_user_model_id()
    root = tk.Tk()
    try:
        ProjectManagerApp(root, config, no_tray=args.no_tray)
    except DataDirectoryError as exc:
        root.withdraw()
        messagebox.showerror("数据目录不可写", str(exc))
        root.destroy()
        return 2
    root.mainloop()
    return 0
