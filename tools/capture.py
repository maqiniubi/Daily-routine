"""v1.3.0 界面验收截图：玻璃拟态悬浮条 + Apple 风格设置中心。

产出到 shots/v12_*.png：
    bar       悬浮条
    tab_sched / tab_week / tab_course / tab_countdown / tab_settings   五个分页
    toast     提醒气泡
    sticker   桌面贴纸
    sponsor   赞赏面板
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="cb_shot12_")

import tkinter as tk

from app import theme, win32util
from app.controller import Controller
from app.models import AppData, Countdown, default_data
from app.store import Store
from app.ui.common import init_style

SHOTS = Path(__file__).resolve().parent.parent / "shots"


def grab(name: str, box: tuple[int, int, int, int]) -> None:
    from PIL import ImageGrab

    SHOTS.mkdir(exist_ok=True)
    ImageGrab.grab(bbox=box).save(str(SHOTS / f"v12_{name}.png"))
    print("shot:", name, box, flush=True)


def wallpaper(w: int, h: int):
    """给悬浮条垫的彩色网格壁纸：能直观看出半透明与圆角是否成立。"""
    from PIL import Image, ImageDraw, ImageTk

    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 3):
        d.rectangle([0, y, w, y + 3],
                    fill=(20 + y * 210 // h, 70 + y * 40 // h, 190 - y * 120 // h))
    for x in range(0, w, 32):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255), width=1)
    for y in range(0, h, 32):
        d.line([(0, y), (w, y)], fill=(255, 140, 70), width=1)
    d.ellipse([w - 420, 40, w - 60, 400], fill=(255, 225, 70))
    return ImageTk.PhotoImage(im)


def main() -> int:
    win32util.enable_dpi_awareness()

    data = AppData(default_data())
    data.countdowns = [
        Countdown(name="期末考试", target="2026-12-30", show_in_bar=True, show_desktop=True),
        Countdown(name="运动会", target="2026-11-08", show_in_bar=True, show_desktop=True),
        Countdown(name="寒假", target="2027-01-20", show_in_bar=False, show_desktop=False),
    ]
    data.settings["show_desktop_countdown"] = True
    data.settings["desktop_pos"] = [60, 120]
    store = Store()
    store.data = data
    store.save()

    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    sw = root.winfo_screenwidth()

    def shot_bar() -> None:
        sw2, bh = root.winfo_screenwidth(), ctl.topbar.height()
        back = tk.Toplevel(root)
        back.overrideredirect(True)
        back.geometry(f"{sw2}x{bh + 90}+0+0")
        photo = wallpaper(sw2, bh + 90)
        holder = tk.Label(back, image=photo, bd=0)
        holder.image = photo
        holder.pack()
        # 悬浮条是 topmost，壁纸背板也得先 topmost 才能压住桌面上的其它窗口；
        # 之后对悬浮条再下发一次 -topmost，同属 topmost 组时后声明的排更前。
        # 直接下发 SetWindowPos：Tk 的 -topmost 属性对「已经是 topmost」的窗口
        # 不会再发一次调用，而 back 这个由后台进程新建的窗口也抢不过前台窗口，
        # 只能靠 HWND_TOPMOST 显式排到 topmost 组最前面（后下发的排更前）。
        win32util.push_topmost(win32util.hwnd_of(back))
        root.update()
        win32util.push_topmost(ctl.topbar._hwnd)
        root.update()
        print("back:", back.winfo_geometry(), back.winfo_viewable(), flush=True)
        grab("bar", (0, 0, sw2, bh + 6))
        back.destroy()
        root.update()

    def shot_sticker() -> None:
        d = ctl.desktop_countdown
        if d is None:
            print("!! sticker missing", flush=True)
            return
        # 贴纸是透明窗口，直接截会把桌面上的其它窗口一起拍进来；
        # 垫一张壁纸背板、并把贴纸临时置顶，才能拍到它真实的半透明观感。
        root.update()
        d.update_idletasks()
        x, y = d.winfo_rootx(), d.winfo_rooty()
        w, h = d.winfo_width(), d.winfo_height()
        back = tk.Toplevel(root)
        back.overrideredirect(True)
        back.geometry(f"{w + 48}x{h + 48}+{max(0, x - 24)}+{max(0, y - 24)}")
        photo = wallpaper(w + 48, h + 48)
        holder = tk.Label(back, image=photo, bd=0)
        holder.image = photo
        holder.pack()
        back.attributes("-topmost", True)
        root.update()
        d.attributes("-topmost", True)    # 后声明的 topmost 排在更前，压住背板
        root.update()
        grab("sticker", (x - 12, y - 12, x + w + 12, y + h + 12))
        back.destroy()
        d.attributes("-topmost", False)

    def open_win() -> None:
        ctl.open_settings()
        ctl.main_window.update_idletasks()
        print("win", ctl.main_window.winfo_geometry(), flush=True)

    def shot_tab(name: str, index: int) -> None:
        w = ctl.main_window
        w.nb.select(index)                    # _on_tab_pick 内部同步 tkraise
        w.tabbar.select(index, animated=False)  # 截图不要卡在胶囊滑动中间帧
        w.update_idletasks()
        root.update()               # 只跑一次：多跑会把后面到点的定时器也拉进来（重入乱序）
        w.update_idletasks()
        x, y = w.winfo_rootx(), w.winfo_rooty()
        grab(name, (x, y, x + w.winfo_width(), y + w.winfo_height()))

    sponsor: list = [None]

    def open_sponsor() -> None:
        sponsor[0] = ctl.show_sponsor()

    def shot_sponsor() -> None:
        win = sponsor[0]
        if win is None or not win.winfo_exists():
            print("!! sponsor dialog not found", flush=True)
            return
        win.update_idletasks()
        x, y = win.winfo_rootx(), win.winfo_rooty()
        grab("sponsor", (x, y, x + win.winfo_width(), y + win.winfo_height()))
        win.destroy()

    def shot_toast() -> None:
        ctl.toast.show("到上数学课时间了！", seconds=20)
        for _ in range(10):
            root.update()

    def shot_toast_grab() -> None:
        boxes = []
        for win in list(ctl.toast._toasts):          # 列表里直接就是 Toplevel
            if not win.winfo_exists():
                continue
            win.update_idletasks()
            x, y = win.winfo_rootx(), win.winfo_rooty()
            boxes.append((x - 10, y - 10, x + win.winfo_width() + 10, y + win.winfo_height() + 10))
        print("toast boxes", boxes, flush=True)
        for i, b in enumerate(boxes):
            grab(f"toast{i}", b)

    # 串行链式调度：每次只挂一个定时器，避免 update() 把下一个到点的定时器一起跑掉（会串页）
    steps: list = []

    def chain(*fns) -> None:
        def run(rest=()):
            if not rest:
                return
            rest[0]()
            root.after(900, lambda: run(rest[1:]))

        run(fns)

    root.after(600, lambda: chain(
        shot_bar,
        shot_sticker,
        open_win,
        lambda: shot_tab("tab_sched", 0),
        lambda: shot_tab("tab_week", 1),
        lambda: shot_tab("tab_course", 2),
        lambda: shot_tab("tab_countdown", 3),
        lambda: shot_tab("tab_settings", 4),
        lambda: ctl.main_window.hide(),
        shot_toast,
        shot_toast_grab,
        open_sponsor,
        shot_sponsor,
        root.destroy,
    ))
    root.mainloop()
    print("CAPTURE_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
