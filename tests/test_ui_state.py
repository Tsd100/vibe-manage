from datetime import datetime, timedelta, timezone

from project_manager.ui import (
    WindowState,
    build_manual_override,
    diagnostic_summary,
    is_dark_theme,
    DATETIME_FORMAT,
    format_manual_datetime,
    format_display_datetime,
    format_recent_datetime,
    mousewheel_scroll_units,
    filter_projects_advanced,
    filter_projects,
    has_attention_signal,
    is_reference_project,
    managed_projects,
    parse_manual_datetime,
    normalize_page_name,
    project_summary_counts,
    project_display_path,
    project_detail_fields,
    PRIORITY_OPTIONS,
    GITHUB_OPEN_SOURCE_OPTIONS,
    PHASE_OPTIONS,
    STATUS_OPTIONS,
    status_tone,
    sort_projects,
)


def test_manual_datetime_parser_and_formatter_support_existing_values():
    value = parse_manual_datetime("2026-09-06 08:09:10")
    assert value is not None
    assert value.year == 2026
    assert format_manual_datetime(value) == "2026-09-06 08:09:10"
    assert parse_manual_datetime("2026-09-06") is not None
    assert parse_manual_datetime("2026-09-06T08:09:10") is not None
    assert parse_manual_datetime("") is None
    assert DATETIME_FORMAT == "%Y-%m-%d %H:%M:%S"


def test_display_datetime_removes_iso_separator_timezone_and_microseconds():
    assert format_display_datetime("2026-08-08T10:38:23+08:00") == "2026-08-08 10:38:23"
    assert format_display_datetime("2026-08-08T02:38:10.511198+00:00") == "2026-08-08 10:38:10"
    assert format_display_datetime("2026/9/5 15:36:02") == "2026-09-05 15:36:02"
    assert format_display_datetime("2026-08-08") == "2026-08-08"
    assert format_display_datetime("未知") == "未知"


def test_recent_datetime_uses_today_yesterday_labels_and_full_older_dates():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone(timedelta(hours=8)))

    assert format_recent_datetime("2026-09-06T02:08:09+00:00", now=now) == "今天 10:08:09"
    assert format_recent_datetime("2026-09-05T14:28:19+00:00", now=now) == "昨天 22:28:19"
    assert format_recent_datetime("2026-09-04T10:00:00+00:00", now=now) == "2026-09-04 18:00:00"


def test_manual_edit_options_are_defined_for_dropdowns():
    assert STATUS_OPTIONS[0] == "未确认"
    assert "进行中" in STATUS_OPTIONS
    assert "开发" in PHASE_OPTIONS
    assert "高" in PRIORITY_OPTIONS
    assert GITHUB_OPEN_SOURCE_OPTIONS == ("未确认", "是", "否")


def test_mousewheel_scroll_units_supports_windows_wheel_deltas():
    assert mousewheel_scroll_units(120) == -1
    assert mousewheel_scroll_units(-120) == 1
    assert mousewheel_scroll_units(240) == -2
    assert mousewheel_scroll_units(0) == 0


def test_system_theme_resolution_is_explicit():
    assert is_dark_theme("深色", False) is True
    assert is_dark_theme("浅色", True) is False
    assert is_dark_theme("跟随系统", True) is True
    assert is_dark_theme("跟随系统", False) is False


def test_secondary_page_switch_hides_previous_page(tmp_path):
    import tkinter as tk

    from project_manager.config import AppConfig
    from project_manager.ui import ProjectManagerApp

    root = tk.Tk()
    root.withdraw()
    try:
        app = ProjectManagerApp(
            root,
            AppConfig(repo_root=tmp_path / "repos", data_dir=tmp_path / "data"),
            no_tray=True,
        )
        app.show_page("时间线")
        app.show_page("扫描记录")
        assert app.timeline_page.winfo_manager() == ""
        assert app.scan_page.winfo_manager() == "pack"
    finally:
        root.destroy()


def test_settings_page_exposes_grouped_configuration_sections(tmp_path):
    import tkinter as tk

    from project_manager.config import AppConfig
    from project_manager.storage import JsonStore
    from project_manager.ui import ProjectManagerApp

    data_dir = tmp_path / "data"
    JsonStore(data_dir / "settings.json").save({
        "default_page": "时间线",
        "auto_scan_on_start": False,
    })
    JsonStore(data_dir / "inventory" / "projects-registry.json").save({
        "generated_at": "2026-09-06T12:00:00+08:00",
        "projects": [{
            "id": "alpha",
            "name": "alpha",
            "path": "alpha",
            "created_at": "2026-09-01T10:00:00+08:00",
            "created_at_source": "git_first_commit",
            "last_modified_at": "2026-09-06T12:00:00+08:00",
        }],
    })
    root = tk.Tk()
    root.withdraw()
    try:
        app = ProjectManagerApp(
            root,
            AppConfig(repo_root=tmp_path / "repos", data_dir=data_dir),
            no_tray=True,
        )
        assert app.timeline_page.winfo_manager() == "pack"
        assert app.timeline_tree.get_children()
        assert app.scan_history_tree.winfo_exists()
        assert app.project_sort_var.get() == "最近修改"
        assert app._window_icon is not None
        assert app._taskbar_icon_configured is True
        assert root.bind_all("<MouseWheel>")
        labels: list[str] = []

        def collect(widget: tk.Misc) -> None:
            for child in widget.winfo_children():
                try:
                    text = str(child.cget("text"))
                except tk.TclError:
                    text = ""
                if text:
                    labels.append(text)
                collect(child)

        collect(app.settings_page)
        for expected in ("项目来源", "扫描行为", "显示与布局", "窗口与托盘", "数据与诊断"):
            assert expected in labels
    finally:
        root.destroy()


def test_diagnostic_summary_contains_paths_and_scan_facts_without_secrets(tmp_path):
    summary = diagnostic_summary(
        data_dir=tmp_path / "data",
        repo_roots=(r"D:\Github", r"D:\Work"),
        project_count=7,
        generated_at="2026-09-06T12:00:00+08:00",
    )

    assert str(tmp_path / "data") in summary
    assert "项目根目录数量：2" in summary
    assert "项目数量：7" in summary
    assert "最近扫描：2026-09-06 12:00:00" in summary
    assert "token" not in summary.lower()


def test_close_hides_window_until_tray_exit():
    state = WindowState()
    state.request_close()
    assert state.visible is False
    assert state.exited is False
    state.request_exit()
    assert state.exited is True


def test_filter_projects_matches_name_purpose_and_status():
    projects = [
        {"name": "alpha", "purpose": "金融数据", "manual_status": "进行中"},
        {"name": "beta", "purpose": "视频工具", "manual_status": "暂停"},
    ]
    assert [p["name"] for p in filter_projects(projects, "金融")] == ["alpha"]
    assert [p["name"] for p in filter_projects(projects, "暂停")] == ["beta"]


def test_filter_projects_matches_github_status_and_remote():
    projects = [{
        "name": "demo",
        "purpose": "用途",
        "github_open_source": "是",
        "github_remote_url": "https://github.com/acme/demo",
    }, {"name": "local", "github_open_source": "否"}]
    assert [item["name"] for item in filter_projects(projects, "github.com")] == ["demo"]
    assert [item["name"] for item in filter_projects(projects, "开源")] == ["demo"]


def test_manual_override_keeps_only_editable_fields():
    result = build_manual_override({
        "manual_created_at": "2026-03-01",
        "manual_status": "进行中",
        "manual_phase": "开发",
        "manual_priority": "高",
        "next_action": "补测试",
        "id": "must-not-change",
    })
    assert result == {
        "manual_created_at": "2026-03-01",
        "manual_status": "进行中",
        "manual_phase": "开发",
        "manual_priority": "高",
        "next_action": "补测试",
        "manual_github_open_source": "",
    }


def test_manual_override_includes_github_field():
    result = build_manual_override({"manual_github_open_source": "否"})
    assert result["manual_github_open_source"] == "否"


def test_project_summary_counts_and_status_tone():
    projects = [
        {"manual_status": "进行中"},
        {"manual_status": "开发中"},
        {"manual_status": "需关注"},
        {"manual_status": "已完成"},
        {},
    ]
    assert project_summary_counts(projects) == {"total": 5, "active": 2, "attention": 1}
    assert status_tone(projects[0]) == "active"
    assert status_tone(projects[2]) == "attention"
    assert status_tone(projects[3]) == "neutral"
    assert status_tone(projects[4]) == "neutral"


def test_reference_projects_are_excluded_from_managed_views():
    projects = [
        {"name": "main", "scope": "项目仓库", "path": "Agent/main"},
        {"name": "marked", "scope": "参考仓库", "path": "Agent/marked"},
        {"name": "legacy", "path": "_references/legacy"},
    ]

    assert is_reference_project(projects[1]) is True
    assert is_reference_project(projects[2]) is True
    assert [project["name"] for project in managed_projects(projects)] == ["main"]


def test_advanced_filters_combine_status_phase_and_attention():
    projects = [
        {"name": "active", "manual_status": "进行中", "manual_phase": "开发", "dirty_files": 0,
         "purpose": "有用途"},
        {"name": "paused", "manual_status": "暂停", "manual_phase": "验证", "dirty_files": 2,
         "purpose": "有用途"},
        {"name": "blocked", "manual_status": "阻塞", "manual_phase": "开发", "dirty_files": 0,
         "purpose": "用途待补充"},
    ]
    result = filter_projects_advanced(projects, status_filter="阻塞", phase_filter="开发", attention_only=True)
    assert [project["name"] for project in result] == ["blocked"]
    assert [project["name"] for project in filter_projects_advanced(projects, attention_only=True)] == ["paused", "blocked"]


def test_attention_signal_does_not_infer_from_missing_validation():
    assert has_attention_signal({"manual_status": "进行中", "purpose": "有用途", "dirty_files": 0}) is False
    assert has_attention_signal({"manual_status": "进行中", "purpose": "有用途", "dirty_files": 1}) is True
    assert has_attention_signal({"manual_status": "进行中", "purpose": "用途待补充", "dirty_files": 0}) is True
    assert has_attention_signal({"manual_status": "进行中", "purpose": "有用途", "validation": {"status": "环境阻塞"}}) is True


def test_normalize_page_name_keeps_supported_pages_and_falls_back():
    assert normalize_page_name("项目总览") == "项目总览"
    assert normalize_page_name("时间线") == "时间线"
    assert normalize_page_name("扫描记录") == "扫描记录"
    assert normalize_page_name("未知") == "项目总览"


def test_project_display_path_expands_relative_registry_path_to_windows_absolute_path():
    assert project_display_path(
        {"path": "Agent/firecrawl", "root": r"D:\Github"},
    ) == r"D:\Github\Agent\firecrawl"


def test_filter_placeholders_keep_all_projects_visible():
    projects = [{"name": "alpha", "manual_status": "进行中", "manual_phase": "开发"}]

    assert filter_projects_advanced(projects, status_filter="全部状态", phase_filter="全部阶段") == projects


def test_project_sort_modes_order_projects_by_requested_signal():
    projects = [
        {"name": "beta", "created_at": "2026-09-02", "last_modified_at": "2026-09-04", "manual_status": "未确认", "purpose": "用途"},
        {"name": "alpha", "created_at": "2026-09-01", "last_modified_at": "2026-09-05", "manual_status": "阻塞", "purpose": "用途"},
        {"name": "gamma", "created_at": "2026-09-03", "last_modified_at": "2026-09-03", "manual_status": "未确认", "purpose": "用途"},
    ]

    assert [item["name"] for item in sort_projects(projects, "最近修改")] == ["alpha", "beta", "gamma"]
    assert [item["name"] for item in sort_projects(projects, "创建时间")] == ["gamma", "beta", "alpha"]
    assert [item["name"] for item in sort_projects(projects, "名称")] == ["alpha", "beta", "gamma"]
    assert [item["name"] for item in sort_projects(projects, "关注优先")] == ["alpha", "beta", "gamma"]


def test_project_detail_fields_match_overview_detail_sections():
    fields = project_detail_fields({
        "purpose": "用途说明",
        "manual_status": "进行中",
        "manual_phase": "开发",
        "manual_priority": "高",
        "created_at": "2026-08-01T10:38:23+08:00",
        "created_at_source": "filesystem_estimate",
        "last_modified_at": "2026-08-02T02:38:10.511198+00:00",
        "next_action": "补测试",
        "github_open_source": "是",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "https://github.com/acme/demo",
    })

    assert fields == [
        ("用途", "用途说明"),
        ("阶段 / 优先级", "开发 · 高"),
        ("创建时间", "2026-08-01 10:38:23（filesystem_estimate）"),
        ("最后修改", "2026-08-02 10:38:10"),
        ("下一步", "补测试"),
        ("状态", "进行中"),
        ("GitHub 开源", "是（自动判断）\nhttps://github.com/acme/demo"),
    ]
    assert project_display_path(
        {"path": "Agent/firecrawl"},
        fallback_roots=(r"D:\Github",),
    ) == r"D:\Github\Agent\firecrawl"
