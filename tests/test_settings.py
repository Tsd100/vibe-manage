from project_manager.settings import UiSettings, settings_from_mapping, ui_scale_factor


def test_settings_use_safe_defaults_when_no_saved_values_exist():
    settings = settings_from_mapping({})

    assert settings == UiSettings()
    assert settings.auto_scan_on_start is True


def test_settings_normalize_saved_values_and_reject_invalid_scale():
    settings = settings_from_mapping({
        "scan_max_depth": "7",
        "tray_on_close": False,
        "auto_scan_on_start": True,
        "ui_scale": "150%",
    })

    assert settings.scan_max_depth == 7
    assert settings.tray_on_close is False
    assert settings.auto_scan_on_start is True
    assert settings.ui_scale == "150%"


def test_settings_fall_back_for_invalid_values():
    settings = settings_from_mapping({
        "scan_max_depth": 0,
        "tray_on_close": "not-bool",
        "auto_scan_on_start": "not-bool",
        "ui_scale": "300%",
    })

    assert settings == UiSettings()


def test_ui_scale_is_relative_to_system_scale():
    assert ui_scale_factor("系统", 1.25) == 1.25
    assert ui_scale_factor("150%", 1.25) == 1.875


def test_settings_keep_multiple_repo_roots_and_remove_duplicates(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    settings = settings_from_mapping({
        "repo_roots": [str(first), str(first), f" {second} "],
    }, fallback_repo_roots=("D:/Github",))

    assert settings.repo_roots == (str(first), str(second))


def test_settings_use_fallback_repo_root_when_no_list_is_saved():
    settings = settings_from_mapping({}, fallback_repo_roots=("D:/Github", "D:/Other"))

    assert settings.repo_roots == ("D:/Github", "D:/Other")


def test_settings_keep_valid_column_widths_and_ignore_invalid_values():
    settings = settings_from_mapping({
        "column_widths": {
            "overview": {"name": 320, "status": 140, "modified": "invalid"},
        },
    })

    assert settings.column_widths["overview"]["name"] == 320
    assert settings.column_widths["overview"]["status"] == 140
    assert settings.column_widths["overview"]["modified"] == 150


def test_settings_include_workspace_preferences_with_safe_defaults():
    settings = settings_from_mapping({})

    assert settings.settings_version == 2
    assert settings.default_page == "项目总览"
    assert settings.compact_layout is False
    assert settings.theme_mode == "浅色"
    assert settings.project_sort == "最近修改"


def test_settings_reject_invalid_workspace_preferences():
    settings = settings_from_mapping({
        "settings_version": "bad",
        "default_page": "不存在页面",
        "compact_layout": "yes",
        "theme_mode": "neon",
        "project_sort": "unknown",
    })

    assert settings.settings_version == 2
    assert settings.default_page == "项目总览"
    assert settings.compact_layout is True
    assert settings.theme_mode == "浅色"
    assert settings.project_sort == "最近修改"


def test_settings_keep_valid_project_sort_preference():
    settings = settings_from_mapping({"project_sort": "名称"})

    assert settings.project_sort == "名称"
