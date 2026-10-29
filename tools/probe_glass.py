"""实验：Tk 窗口上哪几种「玻璃」组合真的有效。

测三种：
  A 只开 DWM accent（acrylic/blur），窗口不透明
  B accent + 整窗 -alpha 0.88
  C 只开 -alpha 0.88

结果截到 shots/_glass_*.png，用肉眼判断：背景是否被模糊、文字是否可读。
"""
from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import tkinter as tk
from ctypes import wintypes

os.environ["APPDATA"] = tempfile.mkdtemp(prefix="cb_glass_")
sys.path.insert(0, r"D:\Daily routine\ClassBell")

from PIL import Image, ImageDraw, ImageGrab, ImageTk  # noqa: E402

from app import theme, win32util  # noqa: E402

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetWindowCompositionAttribute.argtypes = [wintypes.HWND, ctypes.c_void_p]


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class WCAD(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t)]


WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4


def accent(hwnd: int, state: int, abgr: int) -> bool:
    if not hwnd:
        return False
    pol = ACCENT_POLICY(state, 2, abgr & 0xFFFFFFFF, 0)
    data = WCAD(WCA_ACCENT_POLICY, ctypes.cast(ctypes.byref(pol), ctypes.c_void_p),
                ctypes.sizeof(pol))
    try:
        return bool(user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data)))
    except Exception as exc:
        print("accent failed:", exc)
        return False


def make_wallpaper(w: int, h: int) -> ImageTk.PhotoImage:
    """彩色背景：斜向渐变色块 + 细格，用来判断「是否被模糊」。"""
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(0, h, 4):
        d.rectangle([0, y, w, y + 4], fill=(30 + y * 200 // h, 90 + y * 60 // h, 200 - y * 150 // h))
    for x in range(0, w, 40):
        d.line([(x, 0), (x, h)], fill=(255, 255, 255), width=2)
    for y in range(0, h, 40):
        d.line([(0, y), (w, y)], fill=(255, 120, 60), width=2)
    d.ellipse([w - 300, 40, w - 40, 300], fill=(255, 220, 60))
    d.text((20, h - 40), "WALLPAPER GRID — 1px 细线用来判断模糊是否生效", fill=(255, 255, 255))
    return ImageTk.PhotoImage(im)


def main() -> None:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)

    W, H = 1000, 420
    bg = tk.Toplevel(root)
    bg.overrideredirect(True)
    bg.geometry(f"{W}x{H}+80+80")
    photo = make_wallpaper(W, H)
    lbl = tk.Label(bg, image=photo, bd=0)
    lbl.image = photo
    lbl.pack()

    panel_w, panel_h = 620, 150
    px, py = 80 + 190, 80 + 130

    modes = [("A_accent", 4, 0.0), ("B_accent_alpha", 4, 0.88), ("C_alpha", -1, 0.88)]

    def run(i: int) -> None:
        if i >= len(modes):
            root.destroy()
            return
        name, state, alpha = modes[i]
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.geometry(f"{panel_w}x{panel_h}+{px}+{py}")
        win.configure(bg="#0b0b0d")
        cv = tk.Canvas(win, bg="#0b0b0d", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(24, 34, anchor="w", text="永恒  ·  玻璃拟态实验", fill="#f5f5f7",
                       font=theme.F(20, True))
        cv.create_text(24, 74, anchor="w", text="正在上课 · 数学   剩余 00:23:41",
                       fill="#a8a8b0", font=theme.F(14))
        cv.create_rectangle(24, 108, panel_w - 24, 116, fill="#2a2a31", outline="")
        cv.create_rectangle(24, 108, 380, 116, fill="#f5f5f7", outline="")
        win.update_idletasks()

        if alpha:
            win.attributes("-alpha", alpha)
        hwnd = win32util.hwnd_of(win)
        ok = accent(hwnd, state, 0xCC201B1B) if state > 0 else False
        print(f"[{name}] hwnd={hwnd} accent_ok={ok} alpha={alpha}")

        def grab() -> None:
            win.update_idletasks()
            root.update()
            x, y = win.winfo_rootx(), win.winfo_rooty()
            ImageGrab.grab(bbox=(x - 30, y - 30, x + panel_w + 30, y + panel_h + 30)).save(
                rf"D:\Daily routine\ClassBell\shots\_glass_{name}.png")
            win.destroy()
            root.after(120, run, i + 1)

        root.after(420, grab)

    root.after(500, run, 0)
    root.mainloop()


if __name__ == "__main__":
    main()
