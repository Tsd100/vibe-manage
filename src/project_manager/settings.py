from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import os
from typing import Any, Mapping


UI_SCALE_OPTIONS = ("系统", "100%", "125%", "150%", "175%", "200%")
DEFAULT_PAGE_OPTIONS = ("项目总览", "时间线", "扫描记录", "设置")
THEME_MODE_OPTIONS = ("浅色", "深色", "跟随系统")
PROJECT_SORT_OPTIONS = ("最近修改", "创建时间", "名称", "关注优先")
DEFAULT_COLUMN_WIDTHS = {
    "overview": {"name": 205, "status": 90, "phase": 90, "modified": 150},
    "timeline": {"at": 155, "project": 150, "type": 95, "summary": 260, "source": 90},
    "scan_history": {"finished_at": 175, "status": 80, "projects": 80, "duration": 85, "roots": 65},
}


def default_column_widths() -> dict[str, dict[str, int]]:
    return deepcopy(DEFAULT_COLUMN_WIDTHS)


def normalize_column_widths(value: Any) -> dict[str, dict[str, int]]:
    result = default_column_widths()
    if not isinstance(value, Mapping):
        return result
    for view, widths in value.items():
        if view not in result or not isinstance(widths, Mapping):
            continue
        for column, raw_width in widths.items():
            if column not in result[view]:
                continue
            try:
                width = int(raw_width)
            except (TypeError, ValueError):
                continue
            if 60 <= width <= 1200:
                result[view][column] = width
    return result


@dataclass(frozen=True)
class UiSettings:
    settings_version: int = 2
    repo_roots: tuple[str, ...] = ()
    scan_max_depth: int = 5
    tray_on_close: bool = True
    auto_scan_on_start: bool = True
    ui_scale: str = "系统"
    default_page: str = "项目总览"
    compact_layout: bool = False
    theme_mode: str = "浅色"
    project_sort: str = "最近修改"
    column_widths: dict[str, dict[str, int]] = field(default_factory=default_column_widths)

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def normalize_repo_roots(values: Any, fallback: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw_values = values if isinstance(values, (list, tuple)) else fallback
    if isinstance(values, str) and values.strip():
        raw_values = (values,)
    if not raw_values:
        raw_values = fallback
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value).strip()
        if not text:
            continue
        key = os.path.normcase(os.path.abspath(os.path.expanduser(text)))
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return tuple(result)


def settings_from_mapping(
    data: Mapping[str, Any] | None,
    fallback_repo_roots: tuple[str, ...] = (),
) -> UiSettings:
    values = data if isinstance(data, Mapping) else {}
    repo_roots = normalize_repo_roots(values.get("repo_roots"), fallback_repo_roots)
    try:
        depth = int(values.get("scan_max_depth", UiSettings.scan_max_depth))
    except (TypeError, ValueError):
        depth = UiSettings.scan_max_depth
    if not 1 <= depth <= 20:
        depth = UiSettings.scan_max_depth
    scale = values.get("ui_scale", UiSettings.ui_scale)
    if scale not in UI_SCALE_OPTIONS:
        scale = UiSettings.ui_scale
    try:
        settings_version = int(values.get("settings_version", UiSettings.settings_version))
    except (TypeError, ValueError):
        settings_version = UiSettings.settings_version
    if settings_version not in {1, UiSettings.settings_version}:
        settings_version = UiSettings.settings_version
    default_page = values.get("default_page", UiSettings.default_page)
    if default_page not in DEFAULT_PAGE_OPTIONS:
        default_page = UiSettings.default_page
    theme_mode = values.get("theme_mode", UiSettings.theme_mode)
    if theme_mode not in THEME_MODE_OPTIONS:
        theme_mode = UiSettings.theme_mode
    project_sort = values.get("project_sort", UiSettings.project_sort)
    if project_sort not in PROJECT_SORT_OPTIONS:
        project_sort = UiSettings.project_sort
    return UiSettings(
        settings_version=UiSettings.settings_version,
        repo_roots=repo_roots,
        scan_max_depth=depth,
        tray_on_close=_bool_value(values.get("tray_on_close"), UiSettings.tray_on_close),
        auto_scan_on_start=_bool_value(values.get("auto_scan_on_start"), UiSettings.auto_scan_on_start),
        ui_scale=scale,
        default_page=default_page,
        compact_layout=_bool_value(values.get("compact_layout"), UiSettings.compact_layout),
        theme_mode=theme_mode,
        project_sort=project_sort,
        column_widths=normalize_column_widths(values.get("column_widths")),
    )


def ui_scale_factor(option: str, system_scale: float) -> float:
    if option == "系统":
        return system_scale
    try:
        return system_scale * (float(option.rstrip("%")) / 100)
    except (AttributeError, ValueError):
        return system_scale
