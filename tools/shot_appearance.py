"""外观页验收截图：默认深色 / 浅色预设 / 悬浮条实拍。

用法：python tools/shot_appearance.py [dark|light|midnight|bar]
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TAG = sys.argv[1] if len(sys.argv) > 1 else "dark"
TMP = tempfile.mkdtemp(prefix="cb_appearance_")
real = Path(os.environ.get("APPDATA", "")) / "ClassBell" / "config.json"
(Path(TMP) / "ClassBell").mkdir(parents=True, exist_ok=True)
if real.exists():
    shutil.copyfile(real, Path(TMP) / "ClassBell" / "config.json")
os.environ["APPDATA"] = TMP

import tkinter as tk                                          # noqa: E402
from PIL import ImageGrab                                     # noqa: E402

from app import theme, win32util                               # noqa: E402
from app.controller import Controller                          # noqa: E402
from app.ui.common import init_style                           # noqa: E402

SHOTS = ROOT / "shots"
SHOTS.mkdir(exist_ok=True)

PRESET = {"dark": "dark", "light": "light", "midnight": "midnight", "bar": "light"}[TAG]


def spin(root, n: int = 20, delay: float = 0.03) -> None:
    for _ in range(n):
        root.update()
        time.sleep(delay)


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    ctl.open_settings()
    mw = ctl.main_window
    spin(root, 12)

    if PRESET != "dark":
        mw.tab_appearance._use_preset(PRESET)
        spin(root, 15)

    mw.tabbar.select(5)
    spin(root, 15)

    if TAG == "bar":
        bar = ctl.topbar
        bar.win.geometry(f"{bar._win_w}x{bar._bar_h}+18+430")
        win32util.set_window_alpha(bar.win, 1.0)
        spin(root, 20)
        x, y = bar.win.winfo_rootx(), bar.win.winfo_rooty()
        w, h = bar.win.winfo_width(), bar.win.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(str(SHOTS / f"appearance_bar_{TAG}.png"))
        print("bar", x, y, w, h)
    else:
        mw.update_idletasks()
        x, y = mw.winfo_rootx(), mw.winfo_rooty()
        w, h = mw.winfo_width(), mw.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(str(SHOTS / f"appearance_{TAG}.png"))
        print("settings", x, y, w, h, "tab =", mw.tabbar.current())

    tab = mw.tab_appearance
    print("ui =", tab._ui)
    print("bar =", tab._bar)
    print("左栏高", tab.scroll.body.winfo_reqheight(), "视口", tab.scroll.winfo_height())
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
