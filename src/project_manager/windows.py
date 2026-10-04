"""Small Windows-specific helpers used by the desktop shell."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Any


WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010


def taskbar_icon_size(dpi: int) -> int:
    target = max(32, round(32 * max(dpi, 96) / 96))
    return next((size for size in (32, 48, 64, 128, 256) if size >= target), 256)


def small_window_icon_size(dpi: int) -> int:
    target = max(16, round(16 * max(dpi, 96) / 96))
    return next((size for size in (16, 20, 24, 32, 48, 64, 128, 256) if size >= target), 256)


def set_windows_window_icon(root: Any, icon_path: str | Path) -> bool:
    """Apply a real ICO to a Tk window handle for reliable taskbar rendering."""

    if os.name != "nt":
        return False

    path = Path(icon_path)
    if not path.exists():
        return False

    if not root.winfo_ismapped():
        def on_map(event: Any) -> None:
            if event.widget is root:
                root.unbind("<Map>", binding_id)
                set_windows_window_icon(root, path)

        binding_id = root.bind("<Map>", on_map, add="+")
        return bool(binding_id)

    try:
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        user32.SendMessageW.restype = ctypes.c_void_p

        user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.GetAncestor.restype = ctypes.c_void_p
        user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]
        user32.GetDpiForWindow.restype = ctypes.c_uint
        child_hwnd = ctypes.c_void_p(int(root.winfo_id()))
        top_level_hwnd = user32.GetAncestor(child_hwnd, 2)  # GA_ROOT
        hwnd = ctypes.c_void_p(top_level_hwnd or child_hwnd.value)
        dpi = int(user32.GetDpiForWindow(hwnd) or 96)
        flags = LR_LOADFROMFILE
        big_size = taskbar_icon_size(dpi)
        big_icon = user32.LoadImageW(None, str(path), IMAGE_ICON, big_size, big_size, flags)
        small_size = small_window_icon_size(dpi)
        small_icon = user32.LoadImageW(None, str(path), IMAGE_ICON, small_size, small_size, flags)
        if not big_icon and not small_icon:
            return False
        if big_icon:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big_icon)
        if small_icon:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small_icon)
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False
