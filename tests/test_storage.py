from project_manager.storage import JsonStore, merge_manual_overrides


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
