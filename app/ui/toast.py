"""非模态提醒气泡：不抢焦点、不出现在任务栏、若干秒后自动消失并可堆叠。

改版为 iOS / macOS 通知样式：
- 用 `-transparentcolor` 把窗口底色抠掉，画出真正的圆角卡片；
- 出现时从屏幕右侧滑入并淡入，消失时淡出，时长 240ms / 160ms；
- 左上角一枚圆点当作「应用标识」，标题加粗，整体靠留白分层。
"""
from __future__ import annotations

import tkinter as tk

from .. import theme, win32util
from .widgets import animate, rounded_points

#: 抠底色（画布上这个颜色会被系统完全透明化）
_MAGIC = "#01020a"


class ToastManager:
    def __init__(self, root, height_provider):
        self.root = root
        self._height_provider = height_provider  # 悬浮条高度，用于避让
        self._toasts: list[tk.Toplevel] = []
        #: 每个气泡的实际像素尺寸。不靠 winfo_reqwidth 读，因为 Canvas 的请求尺寸
        #: 会被窗口 item 撑大，取回来会变成夸张的空壳。
        self._sizes: dict[str, tuple[int, int]] = {}
        #: 鼠标穿透：提醒气泡只是告知，不该挡住下面的操作
        self._through = False

    def set_click_through(self, enable: bool) -> None:
        self._through = bool(enable)
        for win in list(self._toasts):
            try:
                win32util.set_click_through(win, self._through)
            except Exception:
                pass

    def show(self, text: str, subtitle: str = "CLASSCELL 提醒", seconds: int = 5,
             action=None, action_label: str = "") -> None:
        """弹一个气泡。

        `action` 不为空时，气泡底部多一个胶囊按钮（如「取消关机」）——
        这类需要留后悔药的提醒必须能点，所以整个气泡会**临时关掉鼠标穿透**。
        """
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg=_MAGIC)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", _MAGIC)
        except tk.TclError:
            pass

        cv = tk.Canvas(win, bg=_MAGIC, highlightthickness=0, bd=0)
        cv.pack(fill="both", expand=True)

        # 全部用画布图元绘制。之前用 Frame 承载内容，Frame 的直角会把圆角盖掉
        # （内容只内缩 1~2px，而圆角半径有 14dp），看起来就是个方盒子。
        pad_x, pad_y = theme.P(4), theme.P(3)
        dot_d = theme.S(9)
        gap = theme.P(2)
        text_w = theme.S(280)
        width = pad_x * 2 + dot_d + gap + text_w

        f_title, f_msg = theme.T("caption"), theme.T("headline")
        import tkinter.font as tkfont

        fm_title = tkfont.Font(font=f_title)
        fm_msg = tkfont.Font(font=f_msg)
        # 用临时 Label 量出折行后的高度（不 pack，只取请求尺寸）
        probe = tk.Label(win, text=text, font=f_msg, wraplength=text_w, justify="left")
        probe.update_idletasks()
        msg_w, msg_h = probe.winfo_reqwidth(), probe.winfo_reqheight()
        probe.destroy()
        text_w = max(theme.S(180), msg_w)
        width = pad_x * 2 + dot_d + gap + text_w

        title_h = fm_title.metrics("linespace")
        height = max(pad_y * 2 + title_h + theme.S(3) + msg_h,
                     pad_y * 2 + dot_d)

        has_action = action is not None and bool(action_label)
        btn_font = theme.T("subhead")
        fm_btn = tkfont.Font(font=btn_font)
        btn_h = theme.S(24)
        btn_w = fm_btn.measure(action_label) + theme.S(20) if has_action else 0
        if has_action:
            width = max(width, pad_x * 2 + dot_d + gap + btn_w)
            height += theme.S(7) + btn_h

        cv.configure(width=width, height=height)
        win.geometry(f"{width}x{height}")
        self._sizes[str(win)] = (width, height)

        cv.create_polygon(rounded_points(0.5, 0.5, width - 0.5, height - 0.5, theme.R(14)),
                          fill=theme.CARD, outline=theme.LINE, width=1)
        # 左上角圆点当作「应用标识」
        dx = pad_x
        cv.create_oval(dx, pad_y + theme.S(1), dx + dot_d, pad_y + theme.S(1) + dot_d,
                       fill=theme.ACCENT, outline="")
        tx = dx + dot_d + gap
        cv.create_text(tx, pad_y, text=subtitle, anchor="nw", fill=theme.FG3, font=f_title)
        cv.create_text(tx, pad_y + title_h + theme.S(3), text=text, anchor="nw",
                       fill=theme.FG, font=f_msg, width=text_w, justify="left")

        if has_action:
            by = pad_y + title_h + theme.S(3) + msg_h + theme.S(7)
            cv.create_polygon(rounded_points(tx, by, tx + btn_w, by + btn_h, theme.R(8)),
                              fill=theme.glass(theme.CARD, 0.14), outline=theme.LINE, width=1,
                              tags=("toast_action",))
            cv.create_text(tx + btn_w / 2, by + btn_h / 2, text=action_label,
                           fill=theme.FG, font=btn_font, tags=("toast_action",))

            def on_action(_event=None) -> str:
                try:
                    action()
                except Exception:
                    pass
                self._close(win)
                return "break"

            cv.tag_bind("toast_action", "<Button-1>", on_action)
            # 按钮本身也挂一份：tag_bind 在 item 层先跑，返回 "break"
            # 才能挡住下面 canvas 的「点哪关哪」
            cv.tag_bind("toast_action", "<Enter>",
                        lambda e: cv.configure(cursor="hand2"))
            cv.tag_bind("toast_action", "<Leave>",
                        lambda e: cv.configure(cursor=""))

        self._toasts.append(win)
        self._layout()

        win.deiconify()
        hwnd = win32util.hwnd_of(win)
        if hwnd:
            try:
                style = win32util.user32.GetWindowLongW(hwnd, win32util.GWL_EXSTYLE)
                win32util.user32.SetWindowLongW(hwnd, win32util.GWL_EXSTYLE,
                                                style | win32util.WS_EX_TOOLWINDOW | win32util.WS_EX_NOACTIVATE)
            except Exception:
                pass
            win32util.push_topmost(hwnd)
            # 带按钮的气泡必须可点，否则「取消关机」按不到
            if self._through and not has_action:
                win32util.set_click_through(hwnd, True)

        target_x = win.winfo_x()
        target_y = win.winfo_y()
        start_x = win.winfo_screenwidth() + theme.S(8)
        try:
            win.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        def step(t: float) -> None:
            try:
                win.geometry(f"+{int(start_x + (target_x - start_x) * t)}+{target_y}")
                win.attributes("-alpha", 0.06 + 0.94 * t)
            except tk.TclError:
                pass

        animate(win, 240, step)

        # 关闭绑在 Canvas 而不是窗口上：带按钮时 item 的 tag_bind 先执行并返回 "break"，
        # 这样「点按钮」不会连带触发「点哪关哪」。
        cv.bind("<Button-1>", lambda e: self._close(win))
        win.after(max(1, int(seconds)) * 1000, lambda: self._close(win))

    # ---------- 内部 ----------
    def _layout(self) -> None:
        sw = self.root.winfo_screenwidth()
        margin = theme.S(14)
        y = self._height_provider() + theme.S(12)
        for win in self._toasts:
            if not win.winfo_exists():
                continue
            w, h = self._sizes.get(str(win), (theme.S(272), theme.S(64)))
            win.geometry(f"{w}x{h}+{sw - w - margin}+{y}")
            y += h + theme.S(10)

    def _close(self, win: tk.Toplevel) -> None:
        if win not in self._toasts:
            return
        self._toasts.remove(win)
        self._sizes.pop(str(win), None)
        self._layout()

        def step(t: float) -> None:
            try:
                win.attributes("-alpha", 1.0 - t)
            except tk.TclError:
                pass

        def done() -> None:
            try:
                win.destroy()
            except Exception:
                pass

        try:
            animate(win, 160, step, done)
        except Exception:
            done()

    def clear(self) -> None:
        for win in list(self._toasts):
            if win in self._toasts:
                self._toasts.remove(win)
            self._sizes.pop(str(win), None)
            try:
                win.destroy()
            except Exception:
                pass
