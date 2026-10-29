"""临时验证脚本：桌面倒计时贴纸在 Win+D（显示桌面）后能否自己回来。

用法：python tools/check_sticker.py
会临时把 APPDATA 指到临时目录，不污染真实配置。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="cb_stick_"))
os.environ["APPDATA"] = str(TMP)

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]


def rect_of(hwnd: int):
    r = wintypes.RECT()
    if not hwnd or not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right, r.bottom)


def show_desktop() -> None:
    """向 Shell_TrayWnd 发 0x1A3 = 显示桌面（等价 Win+D）。"""
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    out = ctypes.c_size_t()
    if not tray:
        print("!! 找不到 Shell_TrayWnd")
        return
    user32.SendMessageTimeoutW(tray, 0x1A3, 0, 0, 2, 3000, ctypes.byref(out))


def main() -> int:
    from app import config, win32util
    from app.models import AppData, Countdown, default_data
    from app.store import Store
    import tkinter as tk
    from app.controller import Controller

    win32util.enable_dpi_awareness()

    data = AppData(default_data())
    data.countdowns = [Countdown(name="期末考试", target="2026-12-30", show_desktop=True)]
    data.settings["show_desktop_countdown"] = True
    store = Store()
    store.data = data
    store.save()
    print("config:", config.config_file())

    root = tk.Tk()
    root.withdraw()
    ctl = Controller(root)
    checks: list[tuple[str, bool, str]] = []
    before: list[tuple | None] = [None]

    def step1():
        d = ctl.desktop_countdown
        if d is None:
            checks.append(("贴纸窗口已创建", False, "desktop_countdown is None"))
            root.after(100, finish)
            return
        d.update_idletasks()
        h = d._hwnd or win32util.hwnd_of(d)
        checks.append(("贴纸窗口已创建", bool(h), f"hwnd={h}"))
        checks.append(("初始可见", bool(d.winfo_viewable()), f"viewable={d.winfo_viewable()}"))
        checks.append(("初始未最小化", not win32util.is_minimized(h), f"iconic={win32util.is_minimized(h)}"))
        print("rect before:", rect_of(h))
        before[0] = rect_of(h)
        show_desktop()
        root.after(4500, step2)

    def step2():
        d = ctl.desktop_countdown
        h = (d._hwnd if d else 0) or 0
        iconic = win32util.is_minimized(h)
        checks.append(("Win+D 之后自动恢复", (not iconic) and bool(d and d.winfo_viewable()),
                       f"iconic={iconic} viewable={d.winfo_viewable() if d else None}"))
        r = rect_of(h)
        print("rect after:", r)
        checks.append(("位置保持不变", r is not None and r == before[0], f"before={before[0]} after={r}"))
        finish()

    def finish():
        ok = all(c[1] for c in checks)
        for name, passed, detail in checks:
            print(("PASS " if passed else "FAIL ") + name + "  -> " + detail)
        print("\nRESULT:", "ALL PASS" if ok else "HAS FAIL")
        try:
            ctl._shutdown()
        except Exception:
            root.destroy()
        print("tmp:", TMP)

    root.after(1400, step1)
    try:
        root.mainloop()
    except Exception as exc:
        print("mainloop error:", exc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
