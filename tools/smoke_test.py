"""无人值守冒烟测试：启动悬浮条 -> 打开设置中心 -> 弹一次提醒气泡 -> 截图 -> 自动退出。"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import theme, win32util
from app.controller import Controller
from app.ui.common import init_style

SHOTS = Path(__file__).resolve().parent.parent / "shots"


def grab(name: str, box: tuple[int, int, int, int]) -> None:
    try:
        from PIL import ImageGrab

        SHOTS.mkdir(exist_ok=True)
        ImageGrab.grab(bbox=box).save(str(SHOTS / name))
        print("shot:", name)
    except Exception as exc:  # noqa: BLE001
        print("grab failed:", exc)


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    print("dpi scale =", theme.scale(), "screen =", root.winfo_screenwidth(), root.winfo_screenheight())
    ctl = Controller(root)

    def snap_bar() -> None:
        print("topbar height =", ctl.topbar.height(), "| state =", ctl.topbar.lbl_state.cget("text"),
              "| sub =", ctl.topbar.lbl_sub.cget("text"))
        grab("bar.png", (0, 0, root.winfo_screenwidth(), ctl.topbar.height() + 90))

    root.after(900, snap_bar)
    root.after(1400, ctl.open_settings)
    root.after(2600, lambda: ctl.toast.show("到上数学课时间了！", subtitle="第三节 · 10:10"))
    root.after(3400, lambda: print("toasts =", len(ctl.toast._toasts)))

    def snap_win() -> None:
        w = ctl.main_window
        if not w or not w.winfo_exists():
            print("no main window")
            return
        w.update_idletasks()
        x, y = w.winfo_rootx(), w.winfo_rooty()
        grab("settings.png", (x, y, x + w.winfo_width(), y + w.winfo_height()))
        w.nb.select(2)
        root.after(400, lambda: grab("courses.png", (x, y, x + w.winfo_width(), y + w.winfo_height())))

    root.after(2000, snap_win)
    root.after(4200, root.destroy)
    root.mainloop()
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
