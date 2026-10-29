"""退出链路的子进程脚本：验证 ✕ 立即退出、确认框不被悬浮条遮挡。

用法（由 tests/test_quit.py 调用）：
    python tests/_quit_child.py x        # 点击 ✕ 的路径
    python tests/_quit_child.py dialog   # 右键菜单确认框的路径
"""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
import os
import tempfile
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 测试进程一律用临时数据目录：绝不能读写用户真实的 %APPDATA%\ClassBell
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_test_")


from app import theme, win32util
from app.controller import Controller
from app.ui.common import init_style


def _dialog_rects() -> list[tuple[int, int, int, int]]:
    u = ctypes.WinDLL("user32")
    cb_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found: list[tuple[int, int, int, int]] = []

    def cb(h, _):
        if u.IsWindowVisible(h):
            n = u.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 2)
            u.GetWindowTextW(h, buf, n + 2)
            if buf.value == "退出程序":
                r = wintypes.RECT()
                u.GetWindowRect(h, ctypes.byref(r))
                found.append((r.left, r.top, r.right, r.bottom))
        return True

    u.EnumWindows(cb_t(cb), 0)
    return found


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "x"
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)

    def act() -> None:
        if mode == "x":
            print("ACTION quit_app_now", flush=True)
            ctl.quit_app_now()
        elif mode == "items":
            labels = [it[0] for it in ctl.tray._items if it]
            print("TRAY", labels, flush=True)
            print("BAR_TEXT", [w.cget("text") for w in ctl.topbar.win.winfo_children()
                               if isinstance(w, tk.Frame)], flush=True)
            print("DONE", flush=True)
        else:
            print("ACTION quit_app", flush=True)
            ctl.quit_app()

    def inspect() -> None:
        rects = _dialog_rects()
        print("BAR", ctl.topbar.height(), flush=True)
        print("DIALOG", rects, flush=True)
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel) and w.title() == "退出程序":
                w.destroy()

    root.after(700, act)
    if mode == "dialog":
        root.after(1900, inspect)
    if mode == "items":
        root.after(1400, root.destroy)
    root.after(4200, root.destroy)   # 兜底，避免测试挂死
    root.mainloop()
    print("EXITED cleanly", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
