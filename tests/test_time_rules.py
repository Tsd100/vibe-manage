from project_manager.models import derive_creation_time


def test_manual_creation_time_wins():
    result = derive_creation_time("2026-01-01", "2026-02-01", "2026-03-01")
    assert result.value == "2026-03-01"
    assert result.source == "manual"


def test_filesystem_is_estimate_without_git():
    result = derive_creation_time(None, "2026-02-01", None)
    assert result.value == "2026-02-01"
    assert result.source == "filesystem_estimate"


def test_unknown_when_no_source_exists():
    result = derive_creation_time(None, None, None)
    assert result.value is None
    assert result.source == "unknown"
