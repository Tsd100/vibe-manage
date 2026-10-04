from pathlib import Path
from types import SimpleNamespace
import ctypes
import os

import pytest

from project_manager.icon import app_icon_path
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


def test_small_window_icon_size_matches_window_dpi():
    import project_manager.windows as windows_module

    assert hasattr(windows_module, "small_window_icon_size")
    assert windows_module.small_window_icon_size(96) == 16
    assert windows_module.small_window_icon_size(144) == 24
    assert windows_module.small_window_icon_size(192) == 32


@pytest.mark.skipif(os.name != "nt", reason="requires Windows window handles")
def test_icon_is_applied_to_top_level_window_at_current_dpi():
    import tkinter as tk

    root = tk.Tk()
    try:
        assert set_windows_window_icon(root, app_icon_path())
        root.update()
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        user32.GetDpiForWindow.restype = ctypes.c_uint
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
        user32.SendMessageW.restype = ctypes.c_void_p

        hwnd = user32.GetAncestor(ctypes.c_void_p(root.winfo_id()), 2)
        dpi = user32.GetDpiForWindow(hwnd)
        big_icon = user32.SendMessageW(hwnd, 0x007F, ctypes.c_void_p(1), None)
        small_icon = user32.SendMessageW(hwnd, 0x007F, ctypes.c_void_p(0), None)
        assert big_icon
        assert small_icon
        assert _icon_size(big_icon) >= 32 * dpi / 96
        assert _icon_size(small_icon) >= 16 * dpi / 96
    finally:
        root.destroy()


def _icon_size(icon: int) -> int:
    from ctypes import wintypes

    class IconInfo(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    class Bitmap(ctypes.Structure):
        _fields_ = [
            ("bmType", wintypes.LONG),
            ("bmWidth", wintypes.LONG),
            ("bmHeight", wintypes.LONG),
            ("bmWidthBytes", wintypes.LONG),
            ("bmPlanes", wintypes.WORD),
            ("bmBitsPixel", wintypes.WORD),
            ("bmBits", ctypes.c_void_p),
        ]

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(IconInfo)]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    info = IconInfo()
    assert user32.GetIconInfo(icon, ctypes.byref(info))
    try:
        bitmap = Bitmap()
        gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        assert gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
        return bitmap.bmWidth
    finally:
        gdi32.DeleteObject(info.hbmMask)
        gdi32.DeleteObject(info.hbmColor)
