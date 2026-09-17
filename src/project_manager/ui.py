from __future__ import annotations

import calendar as calendar_module
import os
import threading
import tkinter as tk
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Iterable, Mapping

from PIL import ImageTk
import pystray

from .config import AppConfig
from .icon import app_icon_path, create_app_icon
from .scanner import scan_projects
from .scan_history import append_scan_record, build_scan_record, normalize_scan_history
from .settings import (
    DEFAULT_PAGE_OPTIONS,
    PROJECT_SORT_OPTIONS,
    THEME_MODE_OPTIONS,
    UI_SCALE_OPTIONS,
    UiSettings,
    default_column_widths,
    normalize_repo_roots,
    settings_from_mapping,
    ui_scale_factor,
)
from .storage import JsonStore, merge_manual_overrides, preserve_scan_fields
from .timeline import project_events
from .windows import set_windows_window_icon


@dataclass
class WindowState:
    visible: bool = True
    exited: bool = False

    def request_close(self) -> None:
        self.visible = False

    def request_show(self) -> None:
        if not self.exited:
            self.visible = True

    def request_exit(self) -> None:
        self.visible = False
        self.exited = True


def filter_projects(projects: Iterable[Mapping[str, Any]], query: str) -> list[Mapping[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return list(projects)
    return [
        project for project in projects
        if any(needle in value.lower() for value in (
            str(project.get("name", "")),
            str(project.get("path", "")),
            str(project.get("purpose", "")),
            str(project.get("manual_status", "")),
            str(project.get("manual_phase", "")),
            str(project.get("next_action", "")),
            str(project.get("github_remote_url", "")),
            {
                "是": "GitHub 开源",
                "否": "GitHub 未连接",
                "未确认": "GitHub 未确认",
            }.get(str(project.get("github_open_source", "未确认")), "GitHub 未确认"),
        ))
    ]


def mousewheel_scroll_units(delta: int) -> int:
    """Convert a Windows mouse-wheel delta into Tk canvas scroll units."""
    try:
        value = int(delta)
    except (TypeError, ValueError):
        return 0
    if value == 0:
        return 0
    steps = max(1, abs(value) // 120)
    return -steps if value > 0 else steps


def clamp_window_position(
    x: int,
    y: int,
    width: int,
    height: int,
    screen_width: int,
    screen_height: int,
    titlebar_height: int = 40,
    visible_edge_width: int = 120,
) -> tuple[int, int]:
    """Keep enough of a window visible to recover it with the mouse."""
    del height  # The vertical limit is defined by the visible title bar.
    min_x = min(0, -max(1, int(width)) + visible_edge_width)
    max_x = max(min_x, int(screen_width) - visible_edge_width)
    max_y = max(0, int(screen_height) - max(1, int(titlebar_height)))
    return max(min_x, min(int(x), max_x)), max(0, min(int(y), max_y))


def drag_window_position(pointer_x: int, pointer_y: int, offset_x: int, offset_y: int) -> tuple[int, int]:
    """Calculate a new top-level origin while preserving the grab offset."""
    return int(pointer_x) - int(offset_x), int(pointer_y) - int(offset_y)


def is_reference_project(project: Mapping[str, Any]) -> bool:
    """Return whether a registry record belongs to the read-only reference area."""
    scope = str(project.get("scope", "")).strip()
    path = str(project.get("path", "")).replace("\\", "/").strip().lower()
    return scope == "参考仓库" or path == "_references" or path.startswith("_references/")


def managed_projects(projects: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Return project records that belong in progress-management views."""
    return [project for project in projects if not is_reference_project(project)]


def has_attention_signal(project: Mapping[str, Any]) -> bool:
    """Return whether automatic evidence suggests that a project needs review."""
    if status_tone(project) == "attention":
        return True
    try:
        if int(project.get("dirty_files", 0) or 0) > 0:
            return True
    except (TypeError, ValueError):
        if project.get("dirty_files"):
            return True
    purpose = str(project.get("purpose", "")).strip()
    if not purpose or purpose in {"用途待补充", "用途待确认"}:
        return True
    validation = project.get("validation")
    if isinstance(validation, Mapping):
        validation_status = str(validation.get("status", "")).strip().lower()
        if any(token in validation_status for token in ("阻塞", "失败", "error", "blocked", "未通过")):
            return True
    signals = project.get("attention_signals")
    return bool(signals)


def filter_projects_advanced(
    projects: Iterable[Mapping[str, Any]],
    query: str = "",
    status_filter: str = "全部",
    phase_filter: str = "全部",
    attention_only: bool = False,
) -> list[Mapping[str, Any]]:
    """Apply text, manual-field, and automatic-attention filters in order."""
    visible = filter_projects(projects, query)
    if status_filter and status_filter not in {"全部", "全部状态"}:
        visible = [project for project in visible if str(project.get("manual_status", "未确认")) == status_filter]
    if phase_filter and phase_filter not in {"全部", "全部阶段"}:
        visible = [project for project in visible if str(project.get("manual_phase", "未确认")) == phase_filter]
    if attention_only:
        visible = [project for project in visible if has_attention_signal(project)]
    return visible


def status_tone(project: Mapping[str, Any]) -> str:
    """Return a stable visual tone for a project's manually assigned status."""
    status = str(project.get("manual_status", "未确认")).strip()
    if any(token in status for token in ("进行", "开发", "执行")):
        return "active"
    if any(token in status for token in ("暂停", "阻塞", "关注", "风险")):
        return "attention"
    return "neutral"


def project_summary_counts(projects: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Calculate dashboard counters without mutating the project collection."""
    records = list(projects)
    return {
        "total": len(records),
        "active": sum(status_tone(project) == "active" for project in records),
        "attention": sum(status_tone(project) == "attention" for project in records),
    }


def _project_sort_timestamp(project: Mapping[str, Any]) -> str:
    for field in ("last_modified_at", "working_tree_modified_at", "latest_commit_at", "created_at"):
        value = str(project.get(field) or "").strip()
        if value:
            return value
    return ""


def sort_projects(
    projects: Iterable[Mapping[str, Any]],
    sort_mode: str = "最近修改",
) -> list[Mapping[str, Any]]:
    """Return a stable project ordering for the overview table."""
    records = list(projects)
    if sort_mode == "名称":
        return sorted(records, key=lambda item: (str(item.get("name", "")).lower(), str(item.get("id", ""))))
    if sort_mode == "创建时间":
        return sorted(
            records,
            key=lambda item: (str(item.get("manual_created_at") or item.get("created_at") or ""),
                              str(item.get("name", "")).lower()),
            reverse=True,
        )
    if sort_mode == "关注优先":
        records.sort(key=lambda item: str(item.get("name", "")).lower())
        records.sort(key=_project_sort_timestamp, reverse=True)
        return sorted(records, key=has_attention_signal, reverse=True)
    return sorted(
        records,
        key=lambda item: (_project_sort_timestamp(item), str(item.get("name", "")).lower()),
        reverse=True,
    )


SUPPORTED_PAGES = ("项目总览", "时间线", "扫描记录", "设置")


def normalize_page_name(name: str) -> str:
    return name if name in SUPPORTED_PAGES else "项目总览"


def project_display_path(
    project: Mapping[str, Any],
    fallback_roots: Iterable[str | Path] = (),
) -> str:
    """Return a Windows absolute path for both old and new registry records."""
    raw_path = str(project.get("path", "")).strip()
    if not raw_path:
        return "未知"
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    root_value = str(project.get("root", "")).strip()
    if not root_value:
        root_value = next((str(root).strip() for root in fallback_roots if str(root).strip()), "")
    return str(Path(root_value) / path) if root_value else raw_path


def project_detail_fields(project: Mapping[str, Any]) -> list[tuple[str, str]]:
    manual_created = project.get("manual_created_at")
    created_value = manual_created or project.get("created_at") or "未知"
    created_source = "manual" if manual_created else project.get("created_at_source", "unknown")
    github_status = str(project.get("github_open_source") or "未确认")
    github_source = "手动" if str(project.get("github_open_source_source") or "") == "manual" else "自动判断"
    github_value = f"{github_status}（{github_source}）"
    github_remote = str(project.get("github_remote_url") or "").strip()
    if github_remote:
        github_value += f"\n{github_remote}"
    return [
        ("用途", str(project.get("purpose") or "用途待补充")),
        ("阶段 / 优先级", f"{project.get('manual_phase', '未确认')} · {project.get('manual_priority', '未确认')}"),
        ("创建时间", f"{format_display_datetime(created_value)}（{created_source}）"),
        ("最后修改", format_display_datetime(project.get("last_modified_at"))),
        ("下一步", str(project.get("next_action") or "未填写")),
        ("状态", str(project.get("manual_status") or "未确认")),
        ("GitHub 开源", github_value),
    ]


EDITABLE_FIELDS = (
    "manual_created_at", "manual_status", "manual_phase", "manual_priority", "next_action",
    "manual_github_open_source",
)

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
BEIJING_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
STATUS_OPTIONS = ("未确认", "未开始", "进行中", "已完成", "阻塞", "暂停", "归档")
PHASE_OPTIONS = ("未确认", "探索", "规划", "开发", "验证", "维护")
PRIORITY_OPTIONS = ("未确认", "低", "中", "高")
GITHUB_OPEN_SOURCE_OPTIONS = ("未确认", "是", "否")


def format_display_datetime(value: Any) -> str:
    """Format stored timestamps as Beijing time for compact UI display."""
    text = str(value or "").strip()
    if not text:
        return "未知"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    for candidate in (text, text.replace("T", " ")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=BEIJING_TZ)
            else:
                parsed = parsed.astimezone(BEIJING_TZ)
            return parsed.strftime(DATETIME_FORMAT)
        except ValueError:
            continue
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime(DATETIME_FORMAT if "%H" in fmt else "%Y-%m-%d")
        except ValueError:
            continue
    return text


def _parse_datetime_as_beijing(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text or (len(text) == 10 and text[4] == "-" and text[7] == "-"):
        return None
    for candidate in (text, text.replace("T", " ")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=BEIJING_TZ)).astimezone(BEIJING_TZ)
        except ValueError:
            continue
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=BEIJING_TZ)
        except ValueError:
            continue
    return None


def format_recent_datetime(value: Any, now: datetime | None = None) -> str:
    """Use today/yesterday labels for recent values, full Beijing time otherwise."""
    parsed = _parse_datetime_as_beijing(value)
    if parsed is None:
        return format_display_datetime(value)
    reference = now or datetime.now(BEIJING_TZ)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=BEIJING_TZ)
    else:
        reference = reference.astimezone(BEIJING_TZ)
    day_delta = (reference.date() - parsed.date()).days
    if day_delta == 0:
        return f"今天 {parsed:%H:%M:%S}"
    if day_delta == 1:
        return f"昨天 {parsed:%H:%M:%S}"
    return parsed.strftime(DATETIME_FORMAT)


def parse_manual_datetime(value: str | None) -> datetime | None:
    """Parse the hand-entered creation time without changing displayed timestamps."""
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("T", " ")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in (DATETIME_FORMAT, "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def format_manual_datetime(value: datetime) -> str:
    return value.strftime(DATETIME_FORMAT)


THEME = {
    "canvas": "#f3f6fb",
    "sidebar": "#10243e",
    "sidebar_muted": "#9fb4ce",
    "sidebar_active": "#245fc5",
    "card": "#ffffff",
    "line": "#dce5f0",
    "ink": "#152238",
    "muted": "#718198",
    "primary": "#2563eb",
    "primary_soft": "#e7f0ff",
    "active": "#16804b",
    "active_soft": "#e9f8f0",
    "attention": "#c56a14",
    "attention_soft": "#fff4e5",
}
LIGHT_THEME = dict(THEME)
DARK_THEME = {
    "canvas": "#0f172a",
    "sidebar": "#0b1220",
    "sidebar_muted": "#9fb4ce",
    "sidebar_active": "#245fc5",
    "card": "#111c2e",
    "line": "#283a53",
    "ink": "#e5edf9",
    "muted": "#9fb0c8",
    "primary": "#60a5fa",
    "primary_soft": "#1e3a5f",
    "active": "#34d399",
    "active_soft": "#123a30",
    "attention": "#f59e0b",
    "attention_soft": "#3b2a10",
}


def is_dark_theme(mode: str, system_dark: bool) -> bool:
    return mode == "深色" or (mode == "跟随系统" and system_dark)


def _system_theme_is_dark() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except (ImportError, OSError, TypeError, ValueError):
        return False


def apply_theme_mode(mode: str) -> None:
    """Apply the selected palette before widgets are built or after restart."""
    palette = DARK_THEME if is_dark_theme(mode, _system_theme_is_dark()) else LIGHT_THEME
    THEME.clear()
    THEME.update(palette)


def build_manual_override(values: Mapping[str, Any]) -> dict[str, str]:
    return {field: str(values.get(field, "")).strip() for field in EDITABLE_FIELDS}


def diagnostic_summary(
    data_dir: str | Path,
    repo_roots: Iterable[str | Path],
    project_count: int,
    generated_at: str,
) -> str:
    roots = [str(root) for root in repo_roots]
    return "\n".join((
        "项目管理看板诊断摘要",
        f"数据目录：{data_dir}",
        f"项目根目录数量：{len(roots)}",
        f"项目根目录：{'；'.join(roots) or '未配置'}",
        f"项目数量：{project_count}",
        f"最近扫描：{format_display_datetime(generated_at)}",
    ))


class TrayController:
    def __init__(self, app: "ProjectManagerApp") -> None:
        self.app = app
        self.icon: pystray.Icon | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("打开看板", self._open),
            pystray.MenuItem("恢复窗口位置", self._restore),
            pystray.MenuItem("退出应用", self._exit),
        )
        self.icon = pystray.Icon("project-manager", create_app_icon(64), "项目管理看板", menu)
        self.thread = threading.Thread(target=self.icon.run, name="project-manager-tray", daemon=True)
        self.thread.start()

    def _open(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.app.root.after(0, self.app.show_from_tray)

    def _restore(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.app.root.after(0, self.app.restore_window_position)

    def _exit(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.app.root.after(0, self.app.exit_from_tray)

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()


class ProjectManagerApp:
    def __init__(self, root: tk.Tk, config: AppConfig, no_tray: bool = False) -> None:
        self.root = root
        self.config = config
        self.config.ensure_data_dirs()
        self.state = WindowState()
        self.no_tray = no_tray
        self.tray = TrayController(self) if not no_tray else None
        self.projects: list[dict[str, Any]] = []
        self._refreshing = False
        self._window_clamp_pending = False
        self._window_drag_offset: tuple[int, int] | None = None
        self._registry_store = JsonStore(self.config.data_dir / "inventory" / "projects-registry.json")
        self._scan_history_store = JsonStore(self.config.data_dir / "inventory" / "scan-history.json")
        self._overrides_store = JsonStore(self.config.data_dir / "overrides" / "project-overrides.json")
        self._settings_store = JsonStore(self.config.data_dir / "settings.json")
        self.settings = settings_from_mapping(
            self._settings_store.load(default={}) or {},
            fallback_repo_roots=(str(self.config.repo_root),),
        )
        self.scan_history = normalize_scan_history(self._scan_history_store.load(default={}) or {})
        apply_theme_mode(self.settings.theme_mode)
        self.repo_roots = [Path(value) for value in self.settings.repo_roots]
        self.column_widths = self.settings.column_widths
        self._last_saved_column_widths: dict[str, dict[str, int]] = {}
        try:
            self._system_tk_scaling = float(self.root.tk.call("tk", "scaling"))
        except (TypeError, ValueError, tk.TclError):
            self._system_tk_scaling = 1.0
        self._apply_ui_scale()
        self._build_widgets()
        self._load_registry()
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        if self.tray is not None:
            self.tray.start()
        if self.settings.auto_scan_on_start:
            self.root.after(300, self.refresh)

    def _apply_ui_scale(self) -> None:
        scale = ui_scale_factor(self.settings.ui_scale, self._system_tk_scaling)
        self.root.tk.call("tk", "scaling", scale)

    def _repo_roots_text(self) -> str:
        return "\n".join(str(path) for path in self.repo_roots) or "未配置项目根目录"

    def _configure_tree_columns(
        self,
        tree: ttk.Treeview,
        view_name: str,
        columns: tuple[tuple[str, str, int], ...],
    ) -> None:
        saved = self.column_widths.get(view_name, {})
        for column, title, default_width in columns:
            width = int(saved.get(column, default_width))
            tree.heading(column, text=title)
            tree.column(column, width=width, minwidth=60, anchor="w", stretch=False)
        tree.bind(
            "<ButtonRelease-1>",
            lambda _event, current_tree=tree, current_view=view_name: self._persist_tree_columns(
                current_tree, current_view
            ),
            add="+",
        )

    def _persist_tree_columns(self, tree: ttk.Treeview, view_name: str) -> None:
        widths = {column: int(tree.column(column, "width")) for column in tree["columns"]}
        if widths == self._last_saved_column_widths.get(view_name):
            return
        self._last_saved_column_widths[view_name] = widths
        self.column_widths[view_name] = widths
        payload = self.settings.to_mapping()
        payload["column_widths"] = self.column_widths
        self._settings_store.save(payload)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=THEME["canvas"])
        style.configure("Title.TLabel", background=THEME["canvas"], foreground=THEME["ink"],
                        font=("Segoe UI", 19, "bold"))
        style.configure("Subtitle.TLabel", background=THEME["canvas"], foreground=THEME["muted"],
                        font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=THEME["card"], foreground=THEME["ink"],
                        font=("Segoe UI", 11, "bold"))
        style.configure("Hint.TLabel", background=THEME["card"], foreground=THEME["muted"],
                        font=("Segoe UI", 9))
        style.configure("Search.TEntry", padding=(10, 7), fieldbackground=THEME["card"])
        style.configure("Filter.TCombobox", padding=(4, 3), fieldbackground=THEME["card"],
                        foreground=THEME["ink"])
        style.configure("Filter.TCheckbutton", background=THEME["card"], foreground=THEME["muted"],
                        font=("Segoe UI", 9))
        style.configure("Primary.TButton", padding=(12, 7), font=("Segoe UI", 9, "bold"),
                        foreground="#ffffff", background=THEME["primary"])
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9ab5e8")])
        style.configure("Secondary.TButton", padding=(10, 7), font=("Segoe UI", 9),
                        foreground=THEME["ink"], background=THEME["card"])
        style.configure("Project.Treeview", background=THEME["card"], fieldbackground=THEME["card"],
                        foreground=THEME["ink"], rowheight=31 if self.settings.compact_layout else 38, borderwidth=0,
                        font=("Segoe UI", 9))
        style.configure("Project.Treeview.Heading", background=THEME["card"], foreground=THEME["muted"],
                        font=("Segoe UI", 9, "bold"), padding=(7, 8), relief="flat")
        style.map("Project.Treeview", background=[("selected", THEME["primary_soft"])],
                  foreground=[("selected", THEME["ink"])])
        style.configure("Vertical.TScrollbar", background=THEME["line"], troughcolor=THEME["canvas"],
                        bordercolor=THEME["canvas"], arrowcolor=THEME["muted"])

    def _make_stat_card(self, parent: tk.Misc, title: str, variable: tk.StringVar, accent: str) -> tk.Frame:
        card = tk.Frame(parent, bg=THEME["card"], highlightbackground=THEME["line"],
                        highlightthickness=1, bd=0)
        tk.Frame(card, bg=accent, width=5).pack(side=tk.LEFT, fill=tk.Y)
        body = tk.Frame(card, bg=THEME["card"], padx=14, pady=10)
        body.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(body, text=title, bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(body, textvariable=variable, bg=THEME["card"], fg=THEME["ink"],
                 font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(2, 0))
        return card

    def _build_widgets(self) -> None:
        self._window_icon_asset = app_icon_path()
        self._taskbar_icon_configured = False
        if self._window_icon_asset.exists():
            try:
                self.root.iconbitmap(default=str(self._window_icon_asset))
                self._taskbar_icon_configured = True
            except tk.TclError:
                self._taskbar_icon_configured = False
        self._window_icon = ImageTk.PhotoImage(create_app_icon(64), master=self.root)
        self.root.iconphoto(True, self._window_icon)
        self._taskbar_icon_configured = (
            self._taskbar_icon_configured
            and set_windows_window_icon(self.root, self._window_icon_asset)
        )
        self.root.title("项目管理看板")
        self.root.geometry("1280x780")
        self.root.minsize(1020, 640)
        self.root.bind("<Configure>", lambda _event: self._schedule_window_visibility(), add="+")
        self.root.bind("<Control-Shift-r>", self._restore_window_shortcut, add="+")
        self.root.configure(bg=THEME["canvas"])
        self._configure_styles()

        outer = ttk.Frame(self.root, style="App.TFrame", padding=14)
        outer.pack(fill=tk.BOTH, expand=True)
        shell = ttk.Frame(outer, style="App.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(shell, bg=THEME["sidebar"], width=178)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        sidebar_logo_area = tk.Frame(sidebar, bg=THEME["sidebar"], height=116)
        sidebar_logo_area.pack(fill=tk.X, padx=10, pady=(10, 18))
        sidebar_logo_area.pack_propagate(False)
        tk.Label(sidebar_logo_area, text="VIBE\nMANAGE", bg=THEME["sidebar"], fg="#ffffff",
                 font=("Segoe UI", 15, "bold"), justify=tk.LEFT).pack(anchor="w", padx=10, pady=(14, 0))
        self._bind_window_drag(sidebar_logo_area)
        tk.Label(sidebar, text="工作台", bg=THEME["sidebar"], fg="#7188a6",
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=20, pady=(0, 8))
        self.nav_buttons: dict[str, tk.Button] = {}
        for label in SUPPORTED_PAGES:
            button = tk.Button(
                sidebar, text=f"  {label}", anchor="w", relief="flat", bd=0,
                bg=THEME["sidebar_active"] if label == "项目总览" else THEME["sidebar"],
                fg="#ffffff" if label == "项目总览" else THEME["sidebar_muted"],
                activebackground=THEME["sidebar_active"], activeforeground="#ffffff",
                font=("Segoe UI", 10), padx=6, pady=9,
                command=lambda page=label: self.show_page(page),
            )
            button.pack(fill=tk.X, padx=10, pady=2)
            self.nav_buttons[label] = button
        tk.Frame(sidebar, bg="#28415f", height=1).pack(fill=tk.X, padx=18, pady=(28, 14))
        tk.Label(sidebar, text="项目根目录", bg=THEME["sidebar"], fg="#7188a6",
                 font=("Segoe UI", 8, "bold"), anchor="w").pack(fill=tk.X, padx=20)
        self.repo_roots_var = tk.StringVar(value=self._repo_roots_text())
        tk.Label(sidebar, textvariable=self.repo_roots_var, bg=THEME["sidebar"], fg=THEME["sidebar_muted"],
                 font=("Segoe UI", 8), justify=tk.LEFT, anchor="w", wraplength=138).pack(fill=tk.X, padx=20, pady=(5, 0))
        sidebar_drag_area = tk.Frame(sidebar, bg=THEME["sidebar"])
        sidebar_drag_area.pack(fill=tk.BOTH, expand=True)
        self._bind_window_drag(sidebar_drag_area)
        self._window_drag_regions = (sidebar_logo_area, sidebar_drag_area)

        workspace = ttk.Frame(shell, style="App.TFrame", padding=(18, 0, 0, 0))
        workspace.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header = ttk.Frame(workspace, style="App.TFrame")
        header.pack(fill=tk.X)
        title_block = ttk.Frame(header, style="App.TFrame")
        title_block.pack(side=tk.LEFT)
        self.page_title_var = tk.StringVar(value="项目总览")
        self.page_subtitle_var = tk.StringVar(value="集中查看项目用途、开发阶段和最近活动")
        ttk.Label(title_block, textvariable=self.page_title_var, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_block, textvariable=self.page_subtitle_var, style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        self.actions = ttk.Frame(header, style="App.TFrame")
        self.actions.pack(side=tk.RIGHT, anchor="n")
        self.query = tk.StringVar()
        search = ttk.Entry(self.actions, textvariable=self.query, width=25, style="Search.TEntry")
        search.pack(side=tk.LEFT, padx=(0, 8))
        search.insert(0, "搜索项目、用途或状态")
        search.bind("<FocusIn>", lambda _event: search.delete(0, tk.END) if search.get() == "搜索项目、用途或状态" else None)
        search.bind("<KeyRelease>", lambda _event: self._render_projects())
        self.refresh_button = ttk.Button(self.actions, text="刷新扫描", command=self.refresh, style="Primary.TButton")
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 7))
        ttk.Button(self.actions, text="编辑人工字段", command=self.edit_selected, style="Secondary.TButton").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(workspace, textvariable=self.status_var, style="Subtitle.TLabel").pack(anchor="e", pady=(8, 0))

        self.total_var = tk.StringVar(value="0")
        self.active_var = tk.StringVar(value="0")
        self.attention_var = tk.StringVar(value="0")
        self.summary = tk.Frame(workspace, bg=THEME["canvas"])
        self.summary.pack(fill=tk.X, pady=(16, 0))
        for column in range(3):
            self.summary.columnconfigure(column, weight=1)
        self._make_stat_card(self.summary, "项目总数", self.total_var, THEME["primary"]).grid(row=0, column=0, sticky="ew", padx=(0, 7))
        self._make_stat_card(self.summary, "进行中", self.active_var, THEME["active"]).grid(row=0, column=1, sticky="ew", padx=7)
        self._make_stat_card(self.summary, "需要关注", self.attention_var, THEME["attention"]).grid(row=0, column=2, sticky="ew", padx=(7, 0))

        self.overview_panes = ttk.Panedwindow(workspace, orient=tk.HORIZONTAL)
        self.overview_panes.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        left = tk.Frame(self.overview_panes, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1)
        right = tk.Frame(self.overview_panes, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1)
        self.overview_panes.add(left, weight=3)
        self.overview_panes.add(right, weight=4)

        list_header = tk.Frame(left, bg=THEME["card"], padx=16, pady=13)
        list_header.pack(fill=tk.X)
        list_title_row = tk.Frame(list_header, bg=THEME["card"])
        list_title_row.pack(fill=tk.X)
        tk.Label(list_title_row, text="我的项目", bg=THEME["card"], fg=THEME["ink"],
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.list_count_var = tk.StringVar(value="0 个项目")
        tk.Label(list_title_row, textvariable=self.list_count_var, bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(side=tk.RIGHT)
        filter_row = tk.Frame(list_header, bg=THEME["card"])
        filter_row.pack(fill=tk.X, pady=(11, 0))
        self.status_filter_var = tk.StringVar(value="全部状态")
        status_filter = ttk.Combobox(filter_row, textvariable=self.status_filter_var, state="readonly",
                                     values=("全部状态", "未确认", "未开始", "进行中", "已完成", "阻塞", "暂停", "归档"),
                                     width=12, style="Filter.TCombobox")
        status_filter.pack(side=tk.LEFT, padx=(0, 8))
        status_filter.bind("<<ComboboxSelected>>", lambda _event: self._render_projects())
        self.phase_filter_var = tk.StringVar(value="全部阶段")
        phase_filter = ttk.Combobox(filter_row, textvariable=self.phase_filter_var, state="readonly",
                                    values=("全部阶段", "未确认", "探索", "规划", "开发", "验证", "维护"),
                                    width=12, style="Filter.TCombobox")
        phase_filter.pack(side=tk.LEFT, padx=(0, 8))
        phase_filter.bind("<<ComboboxSelected>>", lambda _event: self._render_projects())
        tk.Label(filter_row, text="排序", bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(4, 5))
        self.project_sort_var = tk.StringVar(value=self.settings.project_sort)
        project_sort = ttk.Combobox(filter_row, textvariable=self.project_sort_var, state="readonly",
                                    values=PROJECT_SORT_OPTIONS, width=11, style="Filter.TCombobox")
        project_sort.pack(side=tk.LEFT, padx=(0, 8))
        project_sort.bind("<<ComboboxSelected>>", lambda _event: self._on_project_sort_changed())
        self.attention_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filter_row, text="只看需关注", variable=self.attention_only_var,
                        command=self._render_projects, style="Filter.TCheckbutton").pack(side=tk.LEFT)
        tk.Frame(left, bg=THEME["line"], height=1).pack(fill=tk.X)
        tree_wrap = tk.Frame(left, bg=THEME["card"], padx=9, pady=9)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(tree_wrap, columns=("name", "status", "phase", "modified"),
                                 show="headings", selectmode="browse", style="Project.Treeview")
        self._configure_tree_columns(
            self.tree,
            "overview",
            (("name", "项目", 205), ("status", "状态", 90),
             ("phase", "阶段", 90), ("modified", "最后修改", 150)),
        )
        self.tree.tag_configure("active", foreground=THEME["active"])
        self.tree.tag_configure("attention", foreground=THEME["attention"])
        self.tree.tag_configure("neutral", foreground=THEME["ink"])
        scroll = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=self.tree.yview)
        xscroll = ttk.Scrollbar(tree_wrap, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X, padx=(0, 14))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_header = tk.Frame(right, bg=THEME["card"], padx=18, pady=13)
        detail_header.pack(fill=tk.X)
        detail_title_row = tk.Frame(detail_header, bg=THEME["card"])
        detail_title_row.pack(fill=tk.X)
        tk.Label(detail_title_row, text="项目详情", bg=THEME["card"], fg=THEME["ink"],
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.detail_badge = tk.Label(detail_title_row, text="已选择", bg=THEME["active_soft"], fg=THEME["active"],
                                     font=("Segoe UI", 8, "bold"), padx=9, pady=3)
        self.detail_badge.pack(side=tk.RIGHT)
        tk.Label(detail_header, text="选择左侧项目查看用途、时间线和验证状态", bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        tk.Frame(right, bg=THEME["line"], height=1).pack(fill=tk.X)
        detail_wrap = tk.Frame(right, bg=THEME["card"], padx=18, pady=12)
        detail_wrap.pack(fill=tk.BOTH, expand=True)
        self.detail_canvas = tk.Canvas(detail_wrap, bg=THEME["card"], highlightthickness=0, borderwidth=0)
        detail_scroll = ttk.Scrollbar(detail_wrap, orient=tk.VERTICAL, command=self.detail_canvas.yview)
        self.detail_content = tk.Frame(self.detail_canvas, bg=THEME["card"])
        detail_window = self.detail_canvas.create_window((0, 0), window=self.detail_content, anchor="nw")
        self.detail_content.bind(
            "<Configure>",
            lambda _event: self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all")),
        )
        self.detail_canvas.bind(
            "<Configure>",
            lambda event: self.detail_canvas.itemconfigure(detail_window, width=event.width),
        )
        detail_scroll.configure(command=self.detail_canvas.yview)
        self.detail_canvas.configure(yscrollcommand=detail_scroll.set)
        self.detail_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._build_secondary_pages(workspace)
        self.show_page(self.settings.default_page)
        self.root.after_idle(self._keep_window_visible)

    def _build_secondary_pages(self, workspace: tk.Misc) -> None:
        self.timeline_page = tk.Frame(workspace, bg=THEME["canvas"])
        timeline_toolbar = tk.Frame(self.timeline_page, bg=THEME["canvas"])
        timeline_toolbar.pack(fill=tk.X, pady=(16, 10))
        tk.Label(timeline_toolbar, text="全局时间线", bg=THEME["canvas"], fg=THEME["ink"],
                 font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        filters = tk.Frame(timeline_toolbar, bg=THEME["canvas"])
        filters.pack(side=tk.RIGHT)
        tk.Label(filters, text="项目", bg=THEME["canvas"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.timeline_project_var = tk.StringVar(value="全部")
        self.timeline_project_box = ttk.Combobox(filters, textvariable=self.timeline_project_var,
                                                  state="readonly", values=("全部",), width=18,
                                                  style="Filter.TCombobox")
        self.timeline_project_box.pack(side=tk.LEFT, padx=(5, 10))
        self.timeline_project_box.bind("<<ComboboxSelected>>", lambda _event: self._render_timeline_page())
        tk.Label(filters, text="事件", bg=THEME["canvas"], fg=THEME["muted"],
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.timeline_type_var = tk.StringVar(value="全部")
        self.timeline_type_box = ttk.Combobox(filters, textvariable=self.timeline_type_var,
                                               state="readonly",
                                               values=("全部", "created", "last_modified", "commit", "working_tree", "validation", "manual", "github_open_source"),
                                               width=13, style="Filter.TCombobox")
        self.timeline_type_box.pack(side=tk.LEFT, padx=(5, 0))
        self.timeline_type_box.bind("<<ComboboxSelected>>", lambda _event: self._render_timeline_page())

        timeline_panes = ttk.Panedwindow(self.timeline_page, orient=tk.HORIZONTAL)
        timeline_panes.pack(fill=tk.BOTH, expand=True)
        timeline_left = tk.Frame(timeline_panes, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1)
        timeline_right = tk.Frame(timeline_panes, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1)
        timeline_panes.add(timeline_left, weight=3)
        timeline_panes.add(timeline_right, weight=2)
        self.timeline_tree = ttk.Treeview(
            timeline_left, columns=("at", "project", "type", "summary", "source"),
            show="headings", selectmode="browse", style="Project.Treeview",
        )
        self._configure_tree_columns(
            self.timeline_tree,
            "timeline",
            (("at", "时间", 155), ("project", "项目", 150),
             ("type", "类型", 95), ("summary", "摘要", 260),
             ("source", "来源", 90)),
        )
        timeline_scroll = ttk.Scrollbar(timeline_left, orient=tk.VERTICAL, command=self.timeline_tree.yview)
        timeline_xscroll = ttk.Scrollbar(timeline_left, orient=tk.HORIZONTAL, command=self.timeline_tree.xview)
        self.timeline_tree.configure(yscrollcommand=timeline_scroll.set, xscrollcommand=timeline_xscroll.set)
        self.timeline_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=8)
        timeline_scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 8), pady=8)
        timeline_xscroll.pack(side=tk.BOTTOM, fill=tk.X, padx=8)
        self.timeline_tree.bind("<<TreeviewSelect>>", self._on_timeline_select)
        self.timeline_event_map: dict[str, tuple[dict[str, Any], Any]] = {}

        self.timeline_detail = tk.Text(
            timeline_right, wrap=tk.WORD, state=tk.DISABLED, padx=16, pady=16,
            bg=THEME["card"], fg=THEME["ink"], relief="flat", borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.timeline_detail.tag_configure("title", font=("Segoe UI", 14, "bold"), foreground=THEME["ink"])
        self.timeline_detail.tag_configure("muted", foreground=THEME["muted"])
        self.timeline_detail.pack(fill=tk.BOTH, expand=True)

        self.scan_page = tk.Frame(workspace, bg=THEME["canvas"])
        scan_toolbar = tk.Frame(self.scan_page, bg=THEME["canvas"])
        scan_toolbar.pack(fill=tk.X, pady=(16, 10))
        tk.Label(scan_toolbar, text="扫描记录", bg=THEME["canvas"], fg=THEME["ink"],
                 font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        ttk.Button(scan_toolbar, text="重新扫描", command=self.refresh, style="Primary.TButton").pack(side=tk.RIGHT)
        scan_info = tk.Frame(self.scan_page, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1,
                             padx=18, pady=16)
        scan_info.pack(fill=tk.X)
        self.scan_status_page_var = tk.StringVar(value="已加载快照")
        self.scan_count_var = tk.StringVar(value="0")
        self.scan_generated_var = tk.StringVar(value="未知")
        self.scan_roots_var = tk.StringVar(value=self._repo_roots_text())
        for row, (label, variable) in enumerate((("扫描根目录", self.scan_roots_var),
                                                  ("数据目录", tk.StringVar(value=str(self.config.data_dir))),
                                                  ("仓库数量", self.scan_count_var),
                                                  ("最近扫描", self.scan_generated_var),
                                                  ("状态", self.scan_status_page_var))):
            tk.Label(scan_info, text=label, bg=THEME["card"], fg=THEME["muted"],
                     font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=5)
            tk.Label(scan_info, textvariable=variable, bg=THEME["card"], fg=THEME["ink"],
                     font=("Segoe UI", 9), anchor="w", justify=tk.LEFT, wraplength=650).grid(row=row, column=1, sticky="w", padx=(16, 0), pady=5)
        scan_info.columnconfigure(1, weight=1)
        scan_history = tk.Frame(self.scan_page, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1,
                                padx=12, pady=12)
        scan_history.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        history_header = tk.Frame(scan_history, bg=THEME["card"])
        history_header.pack(fill=tk.X, pady=(0, 8))
        tk.Label(history_header, text="最近扫描记录", bg=THEME["card"], fg=THEME["ink"],
                 font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self.scan_history_detail_var = tk.StringVar(value="扫描完成后会在这里保留时间、耗时和结果。")
        tk.Label(history_header, textvariable=self.scan_history_detail_var, bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 8), anchor="e").pack(side=tk.RIGHT)
        history_wrap = tk.Frame(scan_history, bg=THEME["card"])
        history_wrap.pack(fill=tk.BOTH, expand=True)
        self.scan_history_tree = ttk.Treeview(
            history_wrap,
            columns=("finished_at", "status", "projects", "duration", "roots"),
            show="headings", selectmode="browse", style="Project.Treeview", height=7,
        )
        self._configure_tree_columns(
            self.scan_history_tree,
            "scan_history",
            (("finished_at", "完成时间", 175), ("status", "结果", 80),
             ("projects", "项目数", 80), ("duration", "耗时", 85), ("roots", "根目录", 65)),
        )
        history_scroll = ttk.Scrollbar(history_wrap, orient=tk.VERTICAL, command=self.scan_history_tree.yview)
        self.scan_history_tree.configure(yscrollcommand=history_scroll.set)
        self.scan_history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.scan_history_tree.bind("<<TreeviewSelect>>", self._on_scan_history_select)
        scan_note = tk.Frame(self.scan_page, bg=THEME["card"], highlightbackground=THEME["line"], highlightthickness=1,
                             padx=18, pady=16)
        scan_note.pack(fill=tk.X, pady=(14, 0))
        tk.Label(scan_note, text="只读边界", bg=THEME["card"], fg=THEME["ink"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(scan_note, text="刷新只读取 Git 元数据、README 和文件时间，并把结果写入 D 盘数据目录；不会修改 D:\\Github 下的业务仓库。",
                 bg=THEME["card"], fg=THEME["muted"], font=("Segoe UI", 9),
                 justify=tk.LEFT, anchor="w", wraplength=760).pack(anchor="w", pady=(8, 0))

        self.settings_page = tk.Frame(workspace, bg=THEME["canvas"])
        settings_wrap = tk.Frame(self.settings_page, bg=THEME["canvas"])
        settings_wrap.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        settings_canvas = tk.Canvas(settings_wrap, bg=THEME["canvas"], highlightthickness=0, borderwidth=0)
        settings_scroll = ttk.Scrollbar(settings_wrap, orient=tk.VERTICAL, command=settings_canvas.yview)
        settings_body = tk.Frame(settings_canvas, bg=THEME["canvas"])
        settings_window = settings_canvas.create_window((0, 0), window=settings_body, anchor="nw")
        settings_body.bind("<Configure>", lambda _event: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
        settings_canvas.bind("<Configure>", lambda event: settings_canvas.itemconfigure(settings_window, width=event.width))
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        settings_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        def settings_mousewheel(event: tk.Event) -> str | None:
            """Forward wheel input from settings descendants to the page canvas."""
            try:
                target = self.root.winfo_containing(event.x_root, event.y_root)
            except (AttributeError, tk.TclError):
                return None
            inside_settings = False
            while target is not None:
                if target == self.settings_page:
                    inside_settings = True
                    break
                target = getattr(target, "master", None)
            if not inside_settings:
                return None
            delta = getattr(event, "delta", 0)
            if getattr(event, "num", None) == 4:
                delta = 120
            elif getattr(event, "num", None) == 5:
                delta = -120
            units = mousewheel_scroll_units(delta)
            if units:
                settings_canvas.yview_scroll(units, "units")
                return "break"
            return None

        self.root.bind_all("<MouseWheel>", settings_mousewheel, add="+")
        self.root.bind_all("<Button-4>", settings_mousewheel, add="+")
        self.root.bind_all("<Button-5>", settings_mousewheel, add="+")

        header = tk.Frame(settings_body, bg=THEME["canvas"])
        header.pack(fill=tk.X, pady=(0, 14))
        tk.Label(header, text="设置", bg=THEME["canvas"], fg=THEME["ink"],
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(header, text="参考 skillmanage 的分组设置方式，保存后写入 D 盘数据目录。",
                 bg=THEME["canvas"], fg=THEME["muted"], font=("Segoe UI", 9),
                 justify=tk.LEFT, anchor="w", wraplength=800).pack(anchor="w", pady=(4, 0))

        def make_section(title: str, description: str) -> tk.Frame:
            card = tk.Frame(settings_body, bg=THEME["card"], highlightbackground=THEME["line"],
                            highlightthickness=1, padx=18, pady=14)
            card.pack(fill=tk.X, pady=(0, 12))
            tk.Label(card, text=title, bg=THEME["card"], fg=THEME["ink"],
                     font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w")
            tk.Label(card, text=description, bg=THEME["card"], fg=THEME["muted"],
                     font=("Segoe UI", 8), anchor="w", justify=tk.LEFT,
                     wraplength=800).pack(anchor="w", pady=(3, 10))
            content = tk.Frame(card, bg=THEME["card"])
            content.pack(fill=tk.X)
            return content

        self.settings_root_entry_var = tk.StringVar()
        self.settings_depth_var = tk.StringVar(value=str(self.settings.scan_max_depth))
        self.settings_scale_var = tk.StringVar(value=self.settings.ui_scale)
        self.settings_default_page_var = tk.StringVar(value=self.settings.default_page)
        self.settings_theme_var = tk.StringVar(value=self.settings.theme_mode)
        self.settings_project_sort_var = tk.StringVar(value=self.settings.project_sort)
        self.settings_tray_var = tk.BooleanVar(value=self.settings.tray_on_close)
        self.settings_auto_scan_var = tk.BooleanVar(value=self.settings.auto_scan_on_start)
        self.settings_compact_var = tk.BooleanVar(value=self.settings.compact_layout)
        self.settings_save_status_var = tk.StringVar(value="")

        source = make_section("项目来源", "管理一个或多个 Windows 项目根目录；扫描只读取 Git 元数据、README 和文件时间。")
        roots_input = tk.Frame(source, bg=THEME["card"])
        roots_input.pack(fill=tk.X)
        ttk.Entry(roots_input, textvariable=self.settings_root_entry_var, width=58).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(roots_input, text="选择文件夹", command=self._choose_repo_root).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(roots_input, text="添加", command=self._add_repo_root).pack(side=tk.LEFT, padx=(6, 0))
        roots_list_frame = tk.Frame(source, bg=THEME["card"])
        roots_list_frame.pack(fill=tk.X, pady=(8, 0))
        self.settings_roots_list = tk.Listbox(
            roots_list_frame, height=4, width=80, selectmode=tk.SINGLE,
            bg=THEME["card"], fg=THEME["ink"], highlightbackground=THEME["line"],
            highlightcolor=THEME["primary"], relief="solid", borderwidth=1,
            activestyle="none", font=("Segoe UI", 9), exportselection=False,
        )
        self.settings_roots_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        roots_scroll = ttk.Scrollbar(roots_list_frame, orient=tk.VERTICAL, command=self.settings_roots_list.yview)
        roots_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.settings_roots_list.configure(yscrollcommand=roots_scroll.set)
        for root_path in self.repo_roots:
            self.settings_roots_list.insert(tk.END, str(root_path))
        ttk.Button(source, text="删除选中目录", command=self._remove_repo_root).pack(anchor="e", pady=(6, 0))

        scan = make_section("扫描行为", "控制扫描深度和启动行为；保存后可选择立即重新扫描。")
        scan.columnconfigure(1, weight=1)
        tk.Label(scan, text="扫描最大深度", bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(scan, textvariable=self.settings_depth_var, width=12).grid(row=0, column=1, sticky="w", padx=(18, 0), pady=5)
        tk.Label(scan, text="范围 1—20 层，避免扫描进入过深的依赖目录。", bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 8)).grid(row=0, column=2, sticky="w", padx=(12, 0), pady=5)
        ttk.Checkbutton(scan, text="启动时自动扫描项目", variable=self.settings_auto_scan_var,
                        style="Filter.TCheckbutton").grid(row=1, column=1, sticky="w", padx=(14, 0), pady=5)

        display = make_section("显示与布局", "参考 skillmanage 的显示设置，调整缩放、默认页面和项目列表密度。")
        display.columnconfigure(1, weight=1)
        for row, label, variable, values in (
            (0, "界面缩放", self.settings_scale_var, UI_SCALE_OPTIONS),
            (1, "默认页面", self.settings_default_page_var, DEFAULT_PAGE_OPTIONS),
            (2, "主题", self.settings_theme_var, THEME_MODE_OPTIONS),
            (3, "项目排序", self.settings_project_sort_var, PROJECT_SORT_OPTIONS),
        ):
            tk.Label(display, text=label, bg=THEME["card"], fg=THEME["muted"],
                     font=("Segoe UI", 9, "bold"), anchor="w").grid(row=row, column=0, sticky="w", pady=5)
            ttk.Combobox(display, textvariable=variable, values=values, state="readonly", width=14,
                         style="Filter.TCombobox").grid(row=row, column=1, sticky="w", padx=(18, 0), pady=5)
        ttk.Checkbutton(display, text="紧凑项目列表（减少行高）", variable=self.settings_compact_var,
                        style="Filter.TCheckbutton").grid(row=4, column=1, sticky="w", padx=(14, 0), pady=5)
        ttk.Button(display, text="恢复表格列宽", command=self._reset_layout).grid(row=5, column=1, sticky="w", padx=(14, 0), pady=(7, 3))
        tk.Label(display, text="主题和紧凑布局将在保存并重启后完整应用。", bg=THEME["card"], fg=THEME["muted"],
                 font=("Segoe UI", 8)).grid(row=6, column=1, sticky="w", padx=(18, 0), pady=(0, 3))

        window = make_section("窗口与托盘", "控制关闭窗口后的行为；关闭托盘后，窗口将直接退出应用。")
        ttk.Checkbutton(window, text="关闭窗口时收进系统托盘", variable=self.settings_tray_var,
                        style="Filter.TCheckbutton").pack(anchor="w", padx=(14, 0), pady=3)

        data = make_section("数据与诊断", "数据默认保存在 D 盘；诊断摘要只包含路径、数量和扫描时间，不包含密钥。")
        tk.Label(data, text=f"数据目录：{self.config.data_dir}", bg=THEME["card"], fg=THEME["ink"],
                 font=("Segoe UI", 9), anchor="w", justify=tk.LEFT, wraplength=800).pack(anchor="w")
        data_buttons = ttk.Frame(data)
        data_buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(data_buttons, text="打开数据目录", command=self._open_data_directory).pack(side=tk.LEFT)
        ttk.Button(data_buttons, text="复制诊断摘要", command=self._copy_diagnostics).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(data_buttons, text="恢复默认设置", command=self._reset_settings).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(data_buttons, text="保存设置", command=self._save_settings, style="Primary.TButton").pack(side=tk.RIGHT)
        ttk.Button(data_buttons, text="保存并重新扫描", command=self._save_settings_and_refresh,
                   style="Secondary.TButton").pack(side=tk.RIGHT, padx=(0, 8))
        tk.Label(data, textvariable=self.settings_save_status_var, bg=THEME["card"], fg=THEME["active"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))

        self.secondary_pages = {
            "时间线": self.timeline_page,
            "扫描记录": self.scan_page,
            "设置": self.settings_page,
        }

    def show_page(self, name: str) -> None:
        page_name = normalize_page_name(name)
        for button_name, button in self.nav_buttons.items():
            button.configure(
                bg=THEME["sidebar_active"] if button_name == page_name else THEME["sidebar"],
                fg="#ffffff" if button_name == page_name else THEME["sidebar_muted"],
            )
        self.page_title_var.set(page_name)
        subtitles = {
            "项目总览": "集中查看项目用途、开发阶段和最近活动",
            "时间线": "按项目复盘提交、文件修改、验证和人工记录",
            "扫描记录": "查看最近一次只读扫描的范围、结果和证据边界",
            "设置": "调整扫描、托盘和界面显示策略",
        }
        self.page_subtitle_var.set(subtitles[page_name])
        if page_name == "项目总览":
            self.summary.pack(fill=tk.X, pady=(16, 0))
            self.overview_panes.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
            if not self.actions.winfo_manager():
                self.actions.pack(side=tk.RIGHT, anchor="n")
            for frame in self.secondary_pages.values():
                frame.pack_forget()
        else:
            self.summary.pack_forget()
            self.overview_panes.pack_forget()
            self.actions.pack_forget()
            for frame in self.secondary_pages.values():
                frame.pack_forget()
            self.secondary_pages[page_name].pack(fill=tk.BOTH, expand=True)
            if page_name == "时间线":
                self._render_timeline_page()
            elif page_name == "扫描记录":
                self._update_scan_page()

    def _choose_repo_root(self) -> None:
        initial = self.settings_root_entry_var.get().strip() or str(self.repo_roots[0] if self.repo_roots else self.config.repo_root)
        selected = filedialog.askdirectory(parent=self.root, initialdir=initial, mustexist=True)
        if selected:
            self.settings_root_entry_var.set(selected)

    def _add_repo_root(self) -> None:
        candidate = self.settings_root_entry_var.get().strip()
        if not candidate:
            self.settings_save_status_var.set("请输入或选择文件夹")
            return
        roots = normalize_repo_roots(
            list(self.settings_roots_list.get(0, tk.END)) + [candidate],
        )
        self.settings_roots_list.delete(0, tk.END)
        for root_path in roots:
            self.settings_roots_list.insert(tk.END, root_path)
        self.settings_root_entry_var.set("")
        self.settings_save_status_var.set("目录已加入列表")

    def _remove_repo_root(self) -> None:
        selected = self.settings_roots_list.curselection()
        if not selected:
            self.settings_save_status_var.set("请先选择要删除的目录")
            return
        if self.settings_roots_list.size() <= 1:
            self.settings_save_status_var.set("至少保留一个项目根目录")
            return
        self.settings_roots_list.delete(selected[0])
        self.settings_save_status_var.set("目录已移除，保存后生效")

    def _reset_layout(self) -> None:
        self.column_widths = default_column_widths()
        for tree, view_name in (
            (self.tree, "overview"),
            (self.timeline_tree, "timeline"),
            (self.scan_history_tree, "scan_history"),
        ):
            for column, width in self.column_widths[view_name].items():
                tree.column(column, width=width)
        self._settings_store.save({**self.settings.to_mapping(), "column_widths": self.column_widths})
        self.settings_save_status_var.set("表格列宽已恢复默认")

    def _open_data_directory(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            startfile = getattr(os, "startfile")
            startfile(str(self.config.data_dir))
            self.settings_save_status_var.set("已打开数据目录")
        except (AttributeError, OSError) as exc:
            messagebox.showerror("打开数据目录失败", str(exc), parent=self.root)

    def _copy_diagnostics(self) -> None:
        summary = diagnostic_summary(
            self.config.data_dir,
            self.repo_roots,
            len(self.projects),
            getattr(self, "registry_generated_at", "未知"),
        )
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(summary)
            self.root.update()
            self.settings_save_status_var.set("诊断摘要已复制")
        except tk.TclError as exc:
            messagebox.showerror("复制诊断摘要失败", str(exc), parent=self.root)

    def _reset_settings(self) -> None:
        defaults = settings_from_mapping({}, fallback_repo_roots=(str(self.config.repo_root),))
        self.settings_roots_list.delete(0, tk.END)
        for root_path in defaults.repo_roots:
            self.settings_roots_list.insert(tk.END, root_path)
        self.settings_depth_var.set(str(defaults.scan_max_depth))
        self.settings_scale_var.set(defaults.ui_scale)
        self.settings_default_page_var.set(defaults.default_page)
        self.settings_theme_var.set(defaults.theme_mode)
        self.settings_project_sort_var.set(defaults.project_sort)
        self.project_sort_var.set(defaults.project_sort)
        self.settings_tray_var.set(defaults.tray_on_close)
        self.settings_auto_scan_var.set(defaults.auto_scan_on_start)
        self.settings_compact_var.set(defaults.compact_layout)
        self.settings_save_status_var.set("已恢复默认值，点击保存后生效")

    def _save_settings(self) -> None:
        self.settings = settings_from_mapping({
            "settings_version": 2,
            "repo_roots": list(self.settings_roots_list.get(0, tk.END)),
            "scan_max_depth": self.settings_depth_var.get(),
            "tray_on_close": self.settings_tray_var.get(),
            "auto_scan_on_start": self.settings_auto_scan_var.get(),
            "ui_scale": self.settings_scale_var.get(),
            "default_page": self.settings_default_page_var.get(),
            "compact_layout": self.settings_compact_var.get(),
            "theme_mode": self.settings_theme_var.get(),
            "project_sort": self.settings_project_sort_var.get(),
            "column_widths": self.column_widths,
        })
        self.repo_roots = [Path(value) for value in self.settings.repo_roots]
        self._settings_store.save(self.settings.to_mapping())
        self._apply_ui_scale()
        self.repo_roots_var.set(self._repo_roots_text())
        self.scan_roots_var.set(self._repo_roots_text())
        self.settings_depth_var.set(str(self.settings.scan_max_depth))
        self.settings_scale_var.set(self.settings.ui_scale)
        self.settings_default_page_var.set(self.settings.default_page)
        self.settings_theme_var.set(self.settings.theme_mode)
        self.settings_project_sort_var.set(self.settings.project_sort)
        self.project_sort_var.set(self.settings.project_sort)
        self.settings_tray_var.set(self.settings.tray_on_close)
        self.settings_auto_scan_var.set(self.settings.auto_scan_on_start)
        self.settings_compact_var.set(self.settings.compact_layout)
        self.settings_save_status_var.set("已保存；主题和布局重启后完整应用")
        self.status_var.set("设置已保存")

    def _on_project_sort_changed(self) -> None:
        self._render_projects()
        self.settings_project_sort_var.set(self.project_sort_var.get())
        payload = self.settings.to_mapping()
        payload["project_sort"] = self.project_sort_var.get()
        payload["column_widths"] = self.column_widths
        self._settings_store.save(payload)
        self.settings = settings_from_mapping(payload, fallback_repo_roots=tuple(str(path) for path in self.repo_roots))

    def _save_settings_and_refresh(self) -> None:
        self._save_settings()
        self.refresh()

    def _render_timeline_page(self) -> None:
        visible_projects = managed_projects(self.projects)
        project_names = ["全部"] + [str(project.get("name", "")) for project in visible_projects]
        self.timeline_project_box.configure(values=project_names)
        if self.timeline_project_var.get() not in project_names:
            self.timeline_project_var.set("全部")
        for item in self.timeline_tree.get_children():
            self.timeline_tree.delete(item)
        self.timeline_event_map.clear()
        project_filter = self.timeline_project_var.get()
        type_filter = self.timeline_type_var.get()
        records: list[tuple[dict[str, Any], Any]] = []
        for project in visible_projects:
            if project_filter != "全部" and str(project.get("name", "")) != project_filter:
                continue
            for event in project_events(project):
                if type_filter != "全部" and event.event_type != type_filter:
                    continue
                records.append((project, event))
        records.sort(key=lambda pair: (pair[1].at is not None, pair[1].at or ""), reverse=True)
        for index, (project, event) in enumerate(records):
            item_id = f"event:{index}"
            self.timeline_event_map[item_id] = (project, event)
            self.timeline_tree.insert(
                "", tk.END, iid=item_id,
                values=(format_display_datetime(event.at), project.get("name", ""), event.event_type,
                        event.summary, event.source),
            )
        if records:
            first_id = "event:0"
            self.timeline_tree.selection_set(first_id)
            self.timeline_tree.focus(first_id)
            self._on_timeline_select(None)
        else:
            self._write_timeline_detail("暂无时间线事件", "调整筛选条件或先执行一次扫描。")

    def _write_timeline_detail(self, title: str, body: str) -> None:
        self.timeline_detail.configure(state=tk.NORMAL)
        self.timeline_detail.delete("1.0", tk.END)
        self.timeline_detail.insert("1.0", title + "\n", "title")
        self.timeline_detail.insert(tk.END, body, "muted")
        self.timeline_detail.configure(state=tk.DISABLED)

    def _on_timeline_select(self, _event: tk.Event | None) -> None:
        selected = self.timeline_tree.selection()
        if not selected or selected[0] not in self.timeline_event_map:
            return
        project, event = self.timeline_event_map[selected[0]]
        body = (
            f"项目：{project.get('name', '')}\n"
            f"时间：{format_display_datetime(event.at)}\n"
            f"事件类型：{event.event_type}\n"
            f"来源：{event.source}\n\n"
            f"摘要：{event.summary}\n\n"
            "来源字段保留原始证据边界，未推断项目完成度。"
        )
        self._write_timeline_detail(event.summary, body)

    def _render_scan_history(self) -> None:
        for item in self.scan_history_tree.get_children():
            self.scan_history_tree.delete(item)
        for index, record in enumerate(self.scan_history):
            duration = record.get("duration_seconds")
            try:
                duration_text = f"{float(duration):.2f} 秒"
            except (TypeError, ValueError):
                duration_text = "未知"
            self.scan_history_tree.insert(
                "", tk.END, iid=f"scan:{index}",
                values=(
                    format_display_datetime(record.get("finished_at") or record.get("started_at")),
                    str(record.get("status") or "未知"),
                    str(record.get("project_count", "未知")),
                    duration_text,
                    str(record.get("root_count", "未知")),
                ),
            )
        if self.scan_history:
            first = "scan:0"
            self.scan_history_tree.selection_set(first)
            self.scan_history_tree.focus(first)
            self._on_scan_history_select(None)
        else:
            self.scan_history_detail_var.set("暂无扫描记录")

    def _on_scan_history_select(self, _event: tk.Event | None) -> None:
        selected = self.scan_history_tree.selection()
        if not selected:
            return
        try:
            record = self.scan_history[int(selected[0].split(":", 1)[1])]
        except (ValueError, IndexError):
            return
        detail = (
            f"{record.get('status', '未知')} · {record.get('project_count', '未知')} 个项目 · "
            f"{record.get('duration_seconds', '未知')} 秒"
        )
        if record.get("error"):
            detail += f" · {record['error']}"
        self.scan_history_detail_var.set(detail)

    def _update_scan_page(self) -> None:
        self.scan_count_var.set(str(len(self.projects)))
        self.scan_generated_var.set(format_display_datetime(getattr(self, "registry_generated_at", "未知")))
        self.scan_roots_var.set(self._repo_roots_text())
        self._render_scan_history()

    def _load_registry(self) -> None:
        payload = self._registry_store.load(default={"projects": []}) or {"projects": []}
        self.registry_generated_at = str(payload.get("generated_at") or "未知")
        self.projects = [dict(project) for project in payload.get("projects", [])]
        self.scan_status_page_var.set("已加载快照")
        self._update_scan_page()
        self._render_projects()
        self._render_timeline_page()
        if not self.projects and self.settings.auto_scan_on_start:
            self.refresh()

    def _render_projects(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        query = self.query.get()
        if query == "搜索项目、用途或状态":
            query = ""
        visible = filter_projects_advanced(
            managed_projects(self.projects),
            query=query,
            status_filter=self.status_filter_var.get(),
            phase_filter=self.phase_filter_var.get(),
            attention_only=self.attention_only_var.get(),
        )
        visible = sort_projects(visible, self.project_sort_var.get())
        managed = managed_projects(self.projects)
        counts = project_summary_counts(managed)
        self.total_var.set(str(counts["total"]))
        self.active_var.set(str(counts["active"]))
        self.attention_var.set(str(counts["attention"]))
        self.list_count_var.set(f"{len(visible)} 个项目")
        for project in visible:
            project_id = str(project.get("id", project.get("path", project.get("name", ""))))
            self.tree.insert(
                "", tk.END, iid=project_id,
                values=(str(project.get("name", "")), project.get("manual_status", "未确认"),
                        project.get("manual_phase", "未确认"), format_recent_datetime(project.get("last_modified_at"))),
                tags=("attention" if has_attention_signal(project) else status_tone(project),),
            )
        visible_ids = [str(project.get("id", project.get("path", project.get("name", "")))) for project in visible]
        selected = self.tree.selection()
        if visible_ids:
            if not selected or selected[0] not in visible_ids:
                self.tree.selection_set(visible_ids[0])
            self._on_select(None)
        else:
            self._on_select(None)
        self.status_var.set(f"显示 {len(visible)}/{len(managed)} 个项目")

    def _status_pill(self, parent: tk.Misc, project: Mapping[str, Any], text: str | None = None) -> tk.Label:
        tone = status_tone(project)
        palette = {
            "active": (THEME["active_soft"], THEME["active"]),
            "attention": (THEME["attention_soft"], THEME["attention"]),
            "neutral": ("#eef2f7", THEME["muted"]),
        }
        background, foreground = palette[tone]
        return tk.Label(
            parent,
            text=text or str(project.get("manual_status") or "未确认"),
            bg=background,
            fg=foreground,
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=3,
        )

    def _render_detail_panel(self, project: Mapping[str, Any] | None) -> None:
        for child in self.detail_content.winfo_children():
            child.destroy()
        if project is None:
            self.detail_badge.configure(text="未选择", bg="#eef2f7", fg=THEME["muted"])
            tk.Label(self.detail_content, text="没有匹配的项目", bg=THEME["card"], fg=THEME["muted"],
                     font=("Segoe UI", 11)).pack(anchor="w", pady=(14, 0))
            return

        self.detail_badge.configure(text="已选择", bg=THEME["active_soft"], fg=THEME["active"])
        tk.Label(self.detail_content, text=str(project.get("name", "项目详情")), bg=THEME["card"],
                 fg=THEME["ink"], font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(2, 0))
        tk.Label(self.detail_content, text=project_display_path(project, self.repo_roots), bg=THEME["card"],
                 fg=THEME["muted"], font=("Segoe UI", 9), anchor="w", justify=tk.LEFT,
                 wraplength=620).pack(anchor="w", pady=(5, 12))
        tk.Frame(self.detail_content, bg=THEME["line"], height=1).pack(fill=tk.X)

        fields = dict(project_detail_fields(project))
        field_grid = tk.Frame(self.detail_content, bg=THEME["card"])
        field_grid.pack(fill=tk.X, pady=(15, 0))
        field_grid.columnconfigure(0, weight=1)
        field_grid.columnconfigure(1, weight=1)

        def add_field(label: str, row: int, column: int, span: int = 1) -> None:
            box = tk.Frame(field_grid, bg=THEME["card"])
            box.grid(row=row, column=column, columnspan=span, sticky="ew", padx=(0 if column == 0 else 12, 0), pady=(0, 13))
            tk.Label(box, text=label, bg=THEME["card"], fg=THEME["muted"],
                     font=("Segoe UI", 8, "bold"), anchor="w").pack(anchor="w")
            if label == "状态":
                self._status_pill(box, project).pack(anchor="w", pady=(5, 0))
            else:
                tk.Label(box, text=fields.get(label, "未知"), bg=THEME["card"], fg=THEME["ink"],
                         font=("Segoe UI", 9), anchor="w", justify=tk.LEFT,
                         wraplength=300).pack(anchor="w", pady=(5, 0))

        add_field("用途", 0, 0, 2)
        add_field("阶段 / 优先级", 1, 0)
        add_field("状态", 1, 1)
        add_field("GitHub 开源", 2, 0, 2)
        add_field("创建时间", 3, 0)
        add_field("最后修改", 3, 1)
        add_field("下一步", 4, 0, 2)

        tk.Label(self.detail_content, text="最近时间线", bg=THEME["card"], fg=THEME["primary"],
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w", pady=(3, 8))
        events = project_events(project)
        if not events:
            tk.Label(self.detail_content, text="暂无可展示事件", bg=THEME["card"], fg=THEME["muted"],
                     font=("Segoe UI", 9)).pack(anchor="w")
        for index, event in enumerate(events):
            event_row = tk.Frame(self.detail_content, bg=THEME["card"])
            event_row.pack(fill=tk.X, pady=(0, 9))
            marker = tk.Frame(event_row, bg=THEME["card"], width=22)
            marker.pack(side=tk.LEFT, fill=tk.Y)
            marker.pack_propagate(False)
            marker_color = THEME["active"] if event.source == "git" else THEME["attention"] if event.source == "manual" else THEME["primary"]
            tk.Label(marker, text="●", bg=THEME["card"], fg=marker_color,
                     font=("Segoe UI", 10)).pack(anchor="n")
            if index < len(events) - 1:
                tk.Frame(marker, bg="#cfe0ff", width=2).place(x=9, y=15, relheight=1.2)
            event_body = tk.Frame(event_row, bg=THEME["card"])
            event_body.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(event_body, text=event.summary, bg=THEME["card"], fg=THEME["ink"],
                     font=("Segoe UI", 9, "bold"), anchor="w", justify=tk.LEFT,
                     wraplength=560).pack(anchor="w")
            tk.Label(event_body, text=f"{format_display_datetime(event.at)} · {event.source}", bg=THEME["card"],
                     fg=THEME["muted"], font=("Segoe UI", 8), anchor="w").pack(anchor="w", pady=(2, 0))

        validation = project.get("validation")
        if isinstance(validation, Mapping):
            tk.Label(self.detail_content, text=f"验证：{validation.get('status', '未验证')} — {validation.get('summary', '')}",
                     bg=THEME["card"], fg=THEME["muted"], font=("Segoe UI", 8),
                     anchor="w", justify=tk.LEFT, wraplength=620).pack(anchor="w", pady=(3, 0))

    def _on_select(self, _event: tk.Event | None) -> None:
        selected = self.tree.selection()
        project = next((item for item in self.projects if item.get("id") == selected[0]), None) if selected else None
        self._render_detail_panel(project)

    def _selected_project(self) -> dict[str, Any] | None:
        selected = self.tree.selection()
        if not selected:
            return None
        return next((item for item in self.projects if item.get("id") == selected[0]), None)

    def _bind_window_drag(self, widget: tk.Misc) -> None:
        widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
        widget.bind("<B1-Motion>", self._drag_window, add="+")

    def _start_window_drag(self, event: tk.Event) -> str:
        self._window_drag_offset = (
            event.x_root - self.root.winfo_x(),
            event.y_root - self.root.winfo_y(),
        )
        return "break"

    def _drag_window(self, event: tk.Event) -> str:
        if self._window_drag_offset is None:
            return "break"
        x, y = drag_window_position(event.x_root, event.y_root, *self._window_drag_offset)
        self.root.geometry(f"+{x}+{y}")
        return "break"

    def _schedule_window_visibility(self) -> None:
        if self._window_clamp_pending:
            return
        self._window_clamp_pending = True
        self.root.after_idle(self._keep_window_visible)

    def _keep_window_visible(self) -> None:
        self._window_clamp_pending = False
        try:
            if self.root.state() != "normal":
                return
            self.root.update_idletasks()
            width = max(1, self.root.winfo_width())
            height = max(1, self.root.winfo_height())
            x, y = clamp_window_position(
                self.root.winfo_x(),
                self.root.winfo_y(),
                width,
                height,
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
            )
            if (x, y) != (self.root.winfo_x(), self.root.winfo_y()):
                self.root.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            return

    def _restore_window_shortcut(self, _event: tk.Event | None = None) -> str:
        self.restore_window_position()
        return "break"

    def restore_window_position(self) -> None:
        """Center the main window so an off-screen title bar can be recovered."""
        try:
            self.root.deiconify()
            self.root.update_idletasks()
            width = max(self.root.winfo_reqwidth(), self.root.winfo_width())
            height = max(self.root.winfo_reqheight(), self.root.winfo_height())
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            x = max(0, (screen_width - width) // 2)
            y = max(0, (screen_height - height) // 2)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            return

    def _center_toplevel(self, window: tk.Toplevel, owner: tk.Misc | None = None) -> None:
        """Center a modal window over the application, with a screen fallback."""
        owner = owner or self.root
        self.root.update_idletasks()
        window.update_idletasks()
        width = max(window.winfo_reqwidth(), window.winfo_width())
        height = max(window.winfo_reqheight(), window.winfo_height())
        owner_width = owner.winfo_width()
        owner_height = owner.winfo_height()
        if owner_width > 1 and owner_height > 1 and owner.winfo_viewable():
            x = owner.winfo_rootx() + max(0, (owner_width - width) // 2)
            y = owner.winfo_rooty() + max(0, (owner_height - height) // 2)
        else:
            x = max(0, (window.winfo_screenwidth() - width) // 2)
            y = max(0, (window.winfo_screenheight() - height) // 2)
        x = min(x, max(0, window.winfo_screenwidth() - width))
        y = min(y, max(0, window.winfo_screenheight() - height))
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _open_datetime_picker(self, parent: tk.Toplevel, target: tk.StringVar) -> None:
        current = parse_manual_datetime(target.get()) or datetime.now().replace(microsecond=0)
        picker = tk.Toplevel(parent)
        picker.title("选择创建时间")
        picker.transient(parent)
        picker.resizable(False, False)

        state: dict[str, Any] = {"selected": current.date()}
        header_var = tk.StringVar()
        hour_var = tk.StringVar(value=f"{current.hour:02d}")
        minute_var = tk.StringVar(value=f"{current.minute:02d}")
        second_var = tk.StringVar(value=f"{current.second:02d}")

        body = ttk.Frame(picker, padding=12)
        body.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(body)
        header.pack(fill=tk.X)
        days_frame = ttk.Frame(body)
        days_frame.pack(fill=tk.X, pady=(8, 6))

        def render_calendar() -> None:
            for child in days_frame.winfo_children():
                child.destroy()
            selected: date = state["selected"]
            header_var.set(f"{selected.year}年 {selected.month}月")
            ttk.Label(days_frame, text="一", width=4, anchor="center").grid(row=0, column=0)
            ttk.Label(days_frame, text="二", width=4, anchor="center").grid(row=0, column=1)
            ttk.Label(days_frame, text="三", width=4, anchor="center").grid(row=0, column=2)
            ttk.Label(days_frame, text="四", width=4, anchor="center").grid(row=0, column=3)
            ttk.Label(days_frame, text="五", width=4, anchor="center").grid(row=0, column=4)
            ttk.Label(days_frame, text="六", width=4, anchor="center").grid(row=0, column=5)
            ttk.Label(days_frame, text="日", width=4, anchor="center").grid(row=0, column=6)
            for row, week in enumerate(calendar_module.monthcalendar(selected.year, selected.month), start=1):
                for column, day_number in enumerate(week):
                    if not day_number:
                        ttk.Label(days_frame, text="", width=4).grid(row=row, column=column, padx=1, pady=1)
                        continue
                    is_selected = day_number == selected.day
                    button = tk.Button(
                        days_frame,
                        text=str(day_number),
                        width=3,
                        relief=tk.SUNKEN if is_selected else tk.RAISED,
                        bd=1,
                        bg="#dbeafe" if is_selected else "#ffffff",
                        activebackground="#bfdbfe",
                        command=lambda value=day_number: choose_day(value),
                    )
                    button.grid(row=row, column=column, padx=1, pady=1)

        def change_month(delta: int) -> None:
            selected: date = state["selected"]
            month_index = selected.year * 12 + selected.month - 1 + delta
            year, month_index = divmod(month_index, 12)
            month = month_index + 1
            day_number = min(selected.day, calendar_module.monthrange(year, month)[1])
            state["selected"] = date(year, month, day_number)
            render_calendar()

        def choose_day(day_number: int) -> None:
            selected: date = state["selected"]
            state["selected"] = date(selected.year, selected.month, day_number)
            render_calendar()

        ttk.Button(header, text="‹", width=3, command=lambda: change_month(-1)).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=header_var, anchor="center", width=16).pack(side=tk.LEFT, expand=True)
        ttk.Button(header, text="›", width=3, command=lambda: change_month(1)).pack(side=tk.RIGHT)
        render_calendar()

        time_frame = ttk.Frame(body)
        time_frame.pack(fill=tk.X, pady=(2, 8))
        ttk.Label(time_frame, text="时间").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Spinbox(time_frame, from_=0, to=23, width=4, textvariable=hour_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="时").pack(side=tk.LEFT, padx=(2, 5))
        ttk.Spinbox(time_frame, from_=0, to=59, width=4, textvariable=minute_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="分").pack(side=tk.LEFT, padx=(2, 5))
        ttk.Spinbox(time_frame, from_=0, to=59, width=4, textvariable=second_var).pack(side=tk.LEFT)
        ttk.Label(time_frame, text="秒").pack(side=tk.LEFT, padx=(2, 0))

        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X)

        def close_picker() -> None:
            try:
                picker.grab_release()
            except tk.TclError:
                pass
            picker.destroy()

        def confirm_picker() -> None:
            try:
                chosen = datetime(
                    state["selected"].year,
                    state["selected"].month,
                    state["selected"].day,
                    int(hour_var.get()),
                    int(minute_var.get()),
                    int(second_var.get()),
                )
            except (TypeError, ValueError):
                messagebox.showwarning("时间格式", "请选择有效的时、分、秒。", parent=picker)
                return
            target.set(format_manual_datetime(chosen))
            close_picker()

        ttk.Button(buttons, text="取消", command=close_picker).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="确定", command=confirm_picker).pack(side=tk.RIGHT)
        picker.protocol("WM_DELETE_WINDOW", close_picker)
        picker.grab_set()
        self._center_toplevel(picker, parent)
        picker.lift()
        picker.focus_force()

    def edit_selected(self) -> None:
        project = self._selected_project()
        if project is None:
            messagebox.showinfo("编辑人工字段", "请先选择一个项目。", parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(f"编辑：{project.get('name', '')}")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        form = ttk.Frame(dialog, padding=14)
        form.pack(fill=tk.BOTH, expand=True)
        variables: dict[str, tk.StringVar] = {}
        labels = {
            "manual_created_at": "手动创建时间",
            "manual_status": "状态",
            "manual_phase": "阶段",
            "manual_priority": "优先级",
            "next_action": "下一步动作",
            "manual_github_open_source": "GitHub 开源",
        }
        for row, field in enumerate(EDITABLE_FIELDS):
            ttk.Label(form, text=labels[field]).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            if field == "manual_github_open_source":
                current_manual = str(project.get(field, "") or "").strip()
                initial_value = current_manual or str(project.get("github_open_source") or "未确认")
            else:
                initial_value = str(project.get(field, ""))
            variable = tk.StringVar(value=initial_value)
            variables[field] = variable
            if field == "manual_created_at":
                date_frame = ttk.Frame(form)
                date_frame.grid(row=row, column=1, sticky="ew", pady=4)
                ttk.Entry(date_frame, textvariable=variable, width=31, state="readonly").pack(side=tk.LEFT, fill=tk.X, expand=True)
                ttk.Button(date_frame, text="选择日期时间", command=lambda value=variable: self._open_datetime_picker(dialog, value)).pack(side=tk.LEFT, padx=(6, 0))
            elif field == "manual_status":
                values = tuple(dict.fromkeys((*STATUS_OPTIONS, str(project.get(field, "")).strip())))
                ttk.Combobox(form, textvariable=variable, values=values, state="readonly", width=43).grid(row=row, column=1, sticky="ew", pady=4)
            elif field == "manual_phase":
                values = tuple(dict.fromkeys((*PHASE_OPTIONS, str(project.get(field, "")).strip())))
                ttk.Combobox(form, textvariable=variable, values=values, state="readonly", width=43).grid(row=row, column=1, sticky="ew", pady=4)
            elif field == "manual_priority":
                values = tuple(dict.fromkeys((*PRIORITY_OPTIONS, str(project.get(field, "")).strip())))
                ttk.Combobox(form, textvariable=variable, values=values, state="readonly", width=43).grid(row=row, column=1, sticky="ew", pady=4)
            elif field == "manual_github_open_source":
                ttk.Combobox(form, textvariable=variable, values=GITHUB_OPEN_SOURCE_OPTIONS,
                             state="readonly", width=43).grid(row=row, column=1, sticky="ew", pady=4)
            else:
                ttk.Entry(form, textvariable=variable, width=46).grid(row=row, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        def close_dialog() -> None:
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            dialog.destroy()

        def save_override() -> None:
            date_value = variables["manual_created_at"].get().strip()
            if date_value and parse_manual_datetime(date_value) is None:
                messagebox.showwarning("时间格式", "请通过“选择日期时间”填写有效的创建时间。", parent=dialog)
                return
            values = {field: variables[field].get() for field in EDITABLE_FIELDS}
            current_github = str(project.get("github_open_source") or "未确认")
            had_manual_github = str(project.get("manual_github_open_source") or "") in {"是", "否"}
            selected_github = values["manual_github_open_source"].strip()
            if selected_github == "未确认" or (not had_manual_github and selected_github == current_github):
                values["manual_github_open_source"] = ""
            override = build_manual_override(values)
            overrides = self._overrides_store.load(default={}) or {}
            overrides[str(project.get("id"))] = override
            self._overrides_store.save(overrides)
            previous_github = str(project.get("github_open_source") or "未确认")
            previous_source = str(project.get("github_open_source_source") or "auto_git_remote")
            manual_github = override["manual_github_open_source"]
            if manual_github in {"是", "否"}:
                effective_github = manual_github
                effective_source = "manual"
            else:
                effective_github = str(project.get("github_auto_open_source") or project.get("github_open_source") or "未确认")
                effective_source = str(project.get("github_auto_open_source_source") or "auto_git_remote")
            project.update(override)
            project["github_open_source"] = effective_github
            project["github_open_source_source"] = effective_source
            if effective_github != previous_github or effective_source != previous_source:
                history = project.get("github_open_source_history")
                history = list(history) if isinstance(history, list) else []
                history.append({
                    "at": datetime.now().astimezone().isoformat(),
                    "value": effective_github,
                    "source": effective_source,
                })
                project["github_open_source_history"] = history
            self._registry_store.save({
                "generated_at": getattr(self, "registry_generated_at", datetime.now().astimezone().isoformat()),
                "projects": self.projects,
            })
            safe_name = str(project.get("id", "project")).replace("/", "__").replace("\\", "__").replace(":", "_")
            JsonStore(self.config.data_dir / "timeline" / f"{safe_name}.json").save(
                [asdict(event) for event in project_events(project)]
            )
            self._render_projects()
            self._on_select(None)
            self._render_timeline_page()
            close_dialog()

        buttons = ttk.Frame(form)
        buttons.grid(row=len(EDITABLE_FIELDS), column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="取消", command=close_dialog).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(buttons, text="保存", command=save_override).pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.grab_set()
        self._center_toplevel(dialog, self.root)
        dialog.lift()
        dialog.focus_force()

    def refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        self.refresh_button.configure(state=tk.DISABLED)
        self.status_var.set("扫描中……")
        threading.Thread(target=self._scan_worker, name="project-manager-scan", daemon=True).start()

    def _scan_worker(self) -> None:
        started_at = datetime.now().astimezone()
        try:
            scanned = scan_projects(self.repo_roots, max_depth=self.settings.scan_max_depth)
            overrides = self._overrides_store.load(default={}) or {}
            previous = {str(item.get("id")): item for item in self.projects}
            merged: list[dict[str, Any]] = []
            for item in scanned:
                record = merge_manual_overrides(item, overrides)
                old = previous.get(str(record.get("id")), {})
                record = preserve_scan_fields(record, old)
                merged.append(record)
            payload = {"generated_at": datetime.now().astimezone().isoformat(), "projects": merged}
            self._registry_store.save(payload)
            for project in merged:
                safe_name = str(project.get("id", "project")).replace("/", "__").replace("\\", "__").replace(":", "_")
                events = [asdict(event) for event in project_events(project)]
                JsonStore(self.config.data_dir / "timeline" / f"{safe_name}.json").save(events)
            finished_at = datetime.now().astimezone()
            scan_record = build_scan_record(
                started_at=started_at,
                finished_at=finished_at,
                status="已完成",
                project_count=len(merged),
                root_count=len(self.repo_roots),
            )
            self.root.after(0, lambda result=scan_record: self._scan_done(merged, None, result))
        except Exception as exc:  # noqa: BLE001 - UI must surface scan failures
            finished_at = datetime.now().astimezone()
            scan_record = build_scan_record(
                started_at=started_at,
                finished_at=finished_at,
                status="失败",
                project_count=0,
                root_count=len(self.repo_roots),
                error=str(exc),
            )
            self.root.after(0, lambda result=scan_record, failure=exc: self._scan_done([], failure, result))

    def _scan_done(
        self,
        projects: list[dict[str, Any]],
        error: Exception | None,
        scan_record: Mapping[str, Any] | None = None,
    ) -> None:
        self._refreshing = False
        self.refresh_button.configure(state=tk.NORMAL)
        if scan_record is not None:
            self.scan_history = append_scan_record(self._scan_history_store, scan_record)
        if error is not None:
            self.scan_status_page_var.set("刷新失败")
            self.status_var.set(f"刷新失败：{error}")
            messagebox.showerror("刷新失败", str(error), parent=self.root)
            return
        self.projects = projects
        self.registry_generated_at = str(scan_record.get("finished_at")) if scan_record else datetime.now().astimezone().isoformat()
        self.scan_status_page_var.set("已完成")
        self._update_scan_page()
        self._render_projects()
        self._render_timeline_page()
        self.status_var.set(f"刷新完成：{len(projects)} 个项目")

    def hide_to_tray(self) -> None:
        if not self.settings.tray_on_close or self.no_tray:
            self.exit_from_tray()
            return
        self.state.request_close()
        self.root.withdraw()

    def show_from_tray(self) -> None:
        self.state.request_show()
        self.root.deiconify()
        self._keep_window_visible()
        self.root.lift()
        self.root.focus_force()

    def exit_from_tray(self) -> None:
        self.state.request_exit()
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()
