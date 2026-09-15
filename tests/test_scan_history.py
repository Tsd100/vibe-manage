from datetime import datetime, timezone, timedelta

from project_manager.scan_history import append_scan_record, build_scan_record, normalize_scan_history
from project_manager.storage import JsonStore


def test_build_scan_record_keeps_duration_and_result_facts():
    started = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=2.345)

    record = build_scan_record(
        started_at=started,
        finished_at=finished,
        status="已完成",
        project_count=41,
        root_count=2,
    )

    assert record["started_at"] == started.isoformat()
    assert record["finished_at"] == finished.isoformat()
    assert record["duration_seconds"] == 2.35
    assert record["project_count"] == 41
    assert record["root_count"] == 2
    assert record["error"] == ""


def test_append_scan_record_persists_newest_first_and_caps_history(tmp_path):
    store = JsonStore(tmp_path / "scan-history.json")
    for index in range(52):
        append_scan_record(store, {"finished_at": str(index), "status": "已完成"})

    records = normalize_scan_history(store.load())
    assert len(records) == 50
    assert records[0]["finished_at"] == "51"
    assert records[-1]["finished_at"] == "2"


def test_normalize_scan_history_rejects_malformed_values():
    assert normalize_scan_history(None) == []
    assert normalize_scan_history({"runs": [{"finished_at": "ok"}, "bad", {}]}) == [{"finished_at": "ok"}]
