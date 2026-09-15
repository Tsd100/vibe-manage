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


def set_windows_window_icon(root: Any, icon_path: str | Path) -> bool:
    """Apply a real ICO to a Tk window handle for reliable taskbar rendering."""

    if os.name != "nt":
        return False

    path = Path(icon_path)
    if not path.exists():
        return False

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

        hwnd = ctypes.c_void_p(int(root.winfo_id()))
        flags = LR_LOADFROMFILE
        big_icon = user32.LoadImageW(None, str(path), IMAGE_ICON, 256, 256, flags)
        small_icon = user32.LoadImageW(None, str(path), IMAGE_ICON, 16, 16, flags)
        if not big_icon and not small_icon:
            return False
        if big_icon:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big_icon)
        if small_icon:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small_icon)
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False
