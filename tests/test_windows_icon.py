from pathlib import Path
from types import SimpleNamespace

from project_manager.windows import set_windows_window_icon, taskbar_icon_size


def test_windows_window_icon_helper_is_safe_off_windows(monkeypatch):
    import project_manager.windows as windows_module

    monkeypatch.setattr(windows_module, "os", SimpleNamespace(name="posix"))

    assert set_windows_window_icon(object(), Path("missing.ico")) is False


def test_taskbar_icon_size_matches_window_dpi():
    assert taskbar_icon_size(96) == 32
    assert taskbar_icon_size(120) == 48
    assert taskbar_icon_size(144) == 48
    assert taskbar_icon_size(192) == 64
