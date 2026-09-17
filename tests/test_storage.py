from project_manager.storage import JsonStore, merge_manual_overrides, preserve_scan_fields


def test_json_store_round_trips(tmp_path):
    store = JsonStore(tmp_path / "registry.json")
    store.save({"projects": [{"id": "repo:demo"}]})
    assert store.load() == {"projects": [{"id": "repo:demo"}]}


def test_missing_store_returns_default(tmp_path):
    assert JsonStore(tmp_path / "missing.json").load(default={"projects": []}) == {"projects": []}


def test_manual_override_survives_auto_refresh():
    auto = {"id": "repo:demo", "purpose": "自动用途", "manual_status": "未确认"}
    overrides = {"repo:demo": {"purpose": "人工用途", "manual_status": "进行中"}}
    merged = merge_manual_overrides(auto, overrides)
    assert merged["purpose"] == "人工用途"
    assert merged["manual_status"] == "进行中"


def test_merge_manual_github_value_overrides_auto_and_empty_restores_auto():
    auto = {
        "id": "repo:demo",
        "github_open_source": "是",
        "github_open_source_source": "auto_git_remote",
        "github_remote_url": "https://github.com/acme/demo",
        "github_auto_open_source": "是",
        "github_auto_open_source_source": "auto_git_remote",
    }
    manual = merge_manual_overrides(auto, {"repo:demo": {"manual_github_open_source": "否"}})
    assert manual["github_open_source"] == "否"
    assert manual["github_open_source_source"] == "manual"
    restored = merge_manual_overrides(auto, {"repo:demo": {"manual_github_open_source": ""}})
    assert restored["github_open_source"] == "是"
    assert restored["github_open_source_source"] == "auto_git_remote"


def test_preserve_scan_fields_keeps_manual_history_across_refresh():
    fresh = {"id": "repo:demo", "github_open_source_history": []}
    previous = {"github_open_source_history": [{"at": "2026-09-06T12:00:00+08:00", "value": "否", "source": "manual"}]}

    merged = preserve_scan_fields(fresh, previous)

    assert merged["github_open_source_history"] == previous["github_open_source_history"]
