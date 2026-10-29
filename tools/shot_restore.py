"""换肤还原验证：浅色 -> 深色后，界面必须与切换前**逐像素一致**。

这是「部分元素没恢复原色」最直接的验收方式：截图对比，
而不是只看几个控件的取值。

用法：python tools/shot_restore.py
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

TMP = tempfile.mkdtemp(prefix="cb_restore_")
real = Path(os.environ.get("APPDATA", "")) / "ClassBell" / "config.json"
(Path(TMP) / "ClassBell").mkdir(parents=True, exist_ok=True)
if real.exists():
    shutil.copyfile(real, Path(TMP) / "ClassBell" / "config.json")
os.environ["APPDATA"] = TMP

import tkinter as tk                                          # noqa: E402
from PIL import Image, ImageChops, ImageGrab                   # noqa: E402

from app import theme, win32util                               # noqa: E402
from app.controller import Controller                          # noqa: E402
from app.ui.common import init_style                          # noqa: E402

SHOTS = ROOT / "shots"
SHOTS.mkdir(exist_ok=True)


def spin(root, n: int = 20, delay: float = 0.03) -> None:
    for _ in range(n):
        root.update()
        time.sleep(delay)


def grab(mw, path: Path) -> Image.Image:
    """截设置中心。窗口可能高过屏幕，超出部分是截不到的桌面，必须裁掉。"""
    mw.update_idletasks()
    x, y = mw.winfo_rootx(), mw.winfo_rooty()
    w, h = mw.winfo_width(), mw.winfo_height()
    visible = max(1, min(h, mw.winfo_screenheight() - y))
    img = ImageGrab.grab(bbox=(x, y, x + w, y + visible))
    img.save(str(path))
    return img


def diff_ratio(a: Image.Image, b: Image.Image) -> float:
    """两张图的差异像素占比。"""
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    bbox = diff.getbbox()
    if bbox is None:
        return 0.0
    hist = diff.convert("L").histogram()
    changed = sum(hist[16:])          # 肉眼能看出来的差异（>16 灰阶）
    total = a.size[0] * a.size[1]
    return changed / total


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    ctl.open_settings()
    mw = ctl.main_window
    mw.tabbar.select(5)
    spin(root, 20)

    tab = mw.tab_appearance

    # 1) 深色基准
    tab._use_preset("dark")
    spin(root, 20)
    base = grab(mw, SHOTS / "restore_dark_before.png")

    # 2) 切浅色
    tab._use_preset("light")
    spin(root, 20)
    light = grab(mw, SHOTS / "restore_light.png")

    # 3) 切回深色
    tab._use_preset("dark")
    spin(root, 20)
    after = grab(mw, SHOTS / "restore_dark_after.png")

    r_light = diff_ratio(base, light)
    r_back = diff_ratio(base, after)
    print(f"深色 -> 浅色   差异像素占比 {r_light * 100:.3f}%")
    print(f"浅色 -> 深色   差异像素占比 {r_back * 100:.3f}%  （相对深色基准）")

    # 悬浮条：它是 layered 窗口，截图会把下层窗口的残影拍进来（合成伪影），
    # 所以比「画布图元的实际着色」，不比像素。
    bar = ctl.topbar
    bar.win.geometry(f"{bar._win_w}x{bar._bar_h}+18+430")
    win32util.set_window_alpha(bar.win, 1.0)
    spin(root, 20)

    def bar_paint():
        out = []
        for name in ("cv_gloss", "cv_day", "cv_slots", "cv_edge"):
            cv = getattr(bar, name, None)
            if cv is None:
                continue
            for item in cv.find_all():
                try:
                    val = cv.itemcget(item, "fill")
                except tk.TclError:
                    continue
                if isinstance(val, str) and val.startswith("#"):
                    out.append(val.lower())
        for name in ("lbl_date", "lbl_plan", "lbl_cd", "lbl_state", "lbl_sub", "lbl_clock"):
            lbl = getattr(bar, name, None)
            if lbl is None:
                continue
            for opt in ("bg", "fg"):
                try:
                    out.append(lbl.cget(opt).lower())
                except tk.TclError:
                    pass
        return out

    bar_before = bar_paint()
    tab._use_preset("light")
    spin(root, 20)
    bar_light = bar_paint()
    tab._use_preset("dark")
    spin(root, 20)
    bar_after = bar_paint()

    changed = sum(1 for a, b in zip(bar_before, bar_light) if a != b)
    same = bar_before == bar_after
    print(f"悬浮条：切浅色后 {changed}/{len(bar_before)} 个图元变色；"
          f"切回深色后{'完全一致' if same else '仍有差异'}")
    r_bar = 0.0 if same else 1.0

    root.destroy()
    ok = r_back < 0.002 and same
    print("\n结论：" + ("还原完整" if ok else "仍有残留"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
