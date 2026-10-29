"""把「24 小时进度条 + 今日时段条」画到一个普通窗口里截图。

悬浮条本身是 layered（整窗 alpha），和正在运行的旧实例叠在一起会拍出重影，
所以这里用一块普通 Canvas 重放同样的绘制代码，只验证图形本身。
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

TAG = sys.argv[1] if len(sys.argv) > 1 else "axis"
TMP = tempfile.mkdtemp(prefix="cb_axis_")
real = Path(os.environ.get("APPDATA", "")) / "ClassBell" / "config.json"
(Path(TMP) / "ClassBell").mkdir(parents=True, exist_ok=True)
if real.exists():
    shutil.copyfile(real, Path(TMP) / "ClassBell" / "config.json")
os.environ["APPDATA"] = TMP

import tkinter as tk                                        # noqa: E402
from PIL import ImageGrab                                   # noqa: E402

from app import theme, win32util                            # noqa: E402
from app.controller import Controller                       # noqa: E402
from app.ui.common import init_style                        # noqa: E402

SHOTS = ROOT / "shots"
SHOTS.mkdir(exist_ok=True)


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    bar = ctl.topbar
    bar._post_init()
    for _ in range(30):
        root.update()
        time.sleep(0.02)

    host = tk.Toplevel(root)
    host.overrideredirect(False)
    host.title("axis")
    host.configure(bg=theme.GLASS)
    w = bar.cv_day.winfo_width() or 1824
    day = tk.Canvas(host, width=w, height=bar.cv_day.winfo_height(), bg=theme.GLASS,
                    highlightthickness=0, bd=0)
    day.pack(padx=theme.P(5), pady=(theme.P(3), theme.S(2)))
    slots = tk.Canvas(host, width=w, height=bar.cv_slots.winfo_height(), bg=theme.GLASS,
                      highlightthickness=0, bd=0)
    slots.pack(padx=theme.P(5), pady=(0, theme.P(3)))

    bar.cv_day, bar.cv_slots = day, slots
    host.geometry("+40+300")
    host.attributes("-topmost", True)
    host.deiconify()
    host.lift()
    host.focus_force()
    host.update_idletasks()
    for _ in range(4):
        host.update()
        time.sleep(0.05)
    bar._draw_day()
    bar._draw_slots()
    for _ in range(3):
        host.lift()
        host.update()
        time.sleep(0.12)
    host.lift()
    host.update()

    x, y = day.winfo_rootx(), day.winfo_rooty()
    hh = slots.winfo_rooty() + slots.winfo_height() - y
    ImageGrab.grab(bbox=(x, y, x + w, y + hh)).save(str(SHOTS / f"axis_{TAG}.png"))
    print("shot:", f"axis_{TAG}.png", (x, y, w, hh))
    print("最后一节 =", bar._last_state["slots"][-1].period.name,
          "| 课程 =", bar._last_state["slots"][-1].label())
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
