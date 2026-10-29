"""实测鼠标穿透：问系统「屏幕上这一点属于谁」。

只看 exstyle 位不算数——`WindowFromPoint` 走的就是真实的命中测试路径，
窗口一旦带上 `WS_EX_TRANSPARENT`，它就会被跳过，返回它**下面**的那个窗口。
所以：

- 穿透关闭 → 命中窗口的根祖先应当是悬浮条自己；
- 穿透开启 → 命中窗口必须是悬浮条以外的窗口（桌面上的其它程序）。

跑法：python tools/probe_clickthrough.py
"""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("APPDATA", tempfile.mkdtemp(prefix="cb_ct_"))

import tkinter as tk  # noqa: E402

from app import theme, win32util  # noqa: E402
from app.controller import Controller  # noqa: E402
from app.ui.common import init_style  # noqa: E402

user32 = ctypes.WinDLL("user32")
user32.WindowFromPoint.restype = wintypes.HWND
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
GA_ROOT = 2


def hit_test(x: int, y: int) -> tuple[int, int, str]:
    """返回 (命中窗口, 它的根祖先, 标题)。"""
    hit = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
    root_hwnd = user32.GetAncestor(wintypes.HWND(hit), GA_ROOT) if hit else 0
    buf = ctypes.create_unicode_buffer(160)
    if hit:
        user32.GetWindowTextW(wintypes.HWND(hit), buf, 160)
    return hit, root_hwnd, buf.value


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    results: dict[str, bool] = {}

    def probe(tag: str) -> None:
        bar = ctl.topbar
        cx = bar._inset + bar._win_w // 2
        cy = bar._off_y + bar._bar_h // 2
        hit, hit_root, title = hit_test(cx, cy)
        on_bar = hit_root == bar._hwnd
        print(f"[{tag}] 点 ({cx},{cy}) 命中 hwnd={hit} root={hit_root} "
              f"'{title}'  落在悬浮条上={on_bar}", flush=True)
        results[tag] = on_bar

    def run() -> None:
        root.update()
        ctl.data.settings["click_through"] = False
        ctl.apply_click_through()
        root.update()
        probe("穿透关闭")

        ctl.data.settings["click_through"] = True
        ctl.apply_click_through()
        root.update()
        probe("穿透开启")

        ok = results.get("穿透关闭") is True and results.get("穿透开启") is False
        print("RESULT", "PASS" if ok else "FAIL", flush=True)
        root.destroy()

    root.after(1000, run)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
