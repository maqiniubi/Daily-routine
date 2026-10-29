"""桌面倒计时贴纸：无边框、不抢焦点、浮动在桌面上。

融合自 CountDay 的「桌面显示」能力，改为 tkinter 实现，零第三方依赖：
- 只显示被标记 show_desktop 的倒计时，竖向排列；
- 拖动移动位置，位置写回数据；
- 双击 / 右键进设置；
- 每 3 秒自动体检：被 Win+D 之类操作最小化后自己恢复显示。

视觉：用 `-transparentcolor` 抠掉窗口底色，卡片是真正的圆角；大号数字配小号单位，
按基线对齐，整体半透明浮在桌面之上。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from .. import theme, win32util
from .widgets import rounded_points

_MAGIC = "#01020a"


class DesktopCountdown(tk.Toplevel):
    def __init__(self, ctl):
        super().__init__(ctl.root)
        self.ctl = ctl
        self.overrideredirect(True)
        self.configure(bg=_MAGIC)
        try:
            self.attributes("-transparentcolor", _MAGIC)
        except tk.TclError:
            self.configure(bg=theme.CARD)
        try:
            self.attributes("-alpha", 0.93)
        except tk.TclError:
            pass
        self.attributes("-topmost", False)
        self._hwnd = 0
        self._through = bool(ctl.data.settings.get("click_through", True))
        self._drag: tuple[int, int] | None = None
        self._job: str | None = None
        self._items = 0
        self._last_xy: tuple[int, int] = (0, 0)

        self._build()
        self.after(60, self._post_init)
        self._tick()

    # ---------------- 构建 ----------------
    def _build(self) -> None:
        for child in self.winfo_children():
            child.destroy()

        self.canvas = tk.Canvas(self, bg=_MAGIC, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        # 窗口尺寸变化后画布尺寸会晚一拍才更新，只在 after_idle 里画会用到旧尺寸，
        # 表现是圆角卡片比窗口小一圈、四周露底色。
        self.canvas.bind("<Configure>", lambda e: self._draw_card())

        # 内容窗口必须内缩一个圆角半径，否则 Frame 的直角会把画出来的圆角盖掉
        self._pad = theme.R(16)
        self.shell = tk.Frame(self.canvas, bg=theme.CARD, padx=theme.P(4), pady=theme.P(3))
        self._win = self.canvas.create_window(self._pad, self._pad, anchor="nw", window=self.shell)

        head_row = tk.Frame(self.shell, bg=theme.CARD)
        head_row.pack(fill="x")
        self.head = tk.Label(head_row, text="倒计时", bg=theme.CARD, fg=theme.FG3,
                             font=theme.T("caption"), anchor="w")
        self.head.pack(side="left")
        # 作者标识：暖金色最省事，也足够在深色卡片上认出来
        self.brand = tk.Label(head_row, text="永恒", bg=theme.CARD,
                              fg=theme.mix(theme.CARD, "#ffd479", 0.62),
                              font=theme.T("caption"), anchor="e")
        self.brand.pack(side="right")

        self.rows = tk.Frame(self.shell, bg=theme.CARD)
        self.rows.pack(fill="x", pady=(theme.S(2), 0))

        for widget in (self, self.canvas, self.shell, head_row, self.head, self.brand, self.rows):
            self._bind_drag(widget)

    def _bind_drag(self, widget) -> None:
        widget.bind("<Button-1>", self._drag_start)
        widget.bind("<B1-Motion>", self._drag_move)
        widget.bind("<ButtonRelease-1>", self._drag_end)
        widget.bind("<Double-Button-1>", lambda e: self.ctl.open_settings())
        widget.bind("<Button-3>", self._menu)

    def _post_init(self) -> None:
        self._hwnd = win32util.hwnd_of(self)
        win32util.make_tool_window(self._hwnd)
        win32util.set_click_through(self._hwnd, self._through)
        self._apply_position()

    def set_click_through(self, enable: bool) -> None:
        """贴纸是「看」的，不该挡住桌面图标的点击。"""
        self._through = bool(enable)
        if self._hwnd:
            win32util.set_click_through(self._hwnd, self._through)

    def _apply_position(self) -> None:
        pos = self.ctl.data.settings.get("desktop_pos")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if not (isinstance(pos, (list, tuple)) and len(pos) >= 2):
            # 首次显示：放到屏幕右侧偏上，避开桌面左上角的图标区
            pos = [sw - theme.S(300), theme.S(180)]
        try:
            x, y = int(pos[0]), int(pos[1])
        except Exception:
            x, y = sw - theme.S(300), theme.S(180)
        try:                               # 不要钻到顶部悬浮条下面去
            min_y = self.ctl.topbar.height() + theme.S(8)
        except Exception:
            min_y = 0
        x = max(0, min(sw - theme.S(120), x))
        y = max(min_y, min(sh - theme.S(80), y))
        self._move_to(x, y)

    def _move_to(self, x: int, y: int) -> None:
        self._last_xy = (int(x), int(y))
        self.geometry(f"+{int(x)}+{int(y)}")

    # ---------------- 交互 ----------------
    def _drag_start(self, event) -> None:
        self._drag = (event.x_root - self._last_xy[0], event.y_root - self._last_xy[1])

    def _drag_move(self, event) -> None:
        if not self._drag:
            return
        x = max(0, event.x_root - self._drag[0])
        y = max(0, event.y_root - self._drag[1])
        self._move_to(x, y)

    def _drag_end(self, _event=None) -> None:
        if not self._drag:
            return
        self._drag = None
        self.ctl.data.settings["desktop_pos"] = [self._last_xy[0], self._last_xy[1]]
        self.ctl.save_data()

    def _menu(self, event) -> None:
        menu = tk.Menu(self, tearoff=0, bg=theme.CARD_HOVER, fg=theme.FG,
                       activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT,
                       bd=0, font=theme.T("body"), activeborderwidth=0)
        menu.add_command(label="打开设置中心", command=self.ctl.open_settings)
        menu.add_command(label="隐藏桌面倒计时", command=self.hide_desktop)
        menu.add_separator()
        menu.add_command(label="打开倒计时设置", command=self._open_countdown_tab)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_countdown_tab(self) -> None:
        self.ctl.open_settings()
        try:
            win = self.ctl.main_window
            win.nb.select(win.tab_countdown)
        except Exception:
            pass

    def hide_desktop(self) -> None:
        self.ctl.data.settings["show_desktop_countdown"] = False
        self.ctl.save_data()
        self.ctl.sync_desktop_countdown()

    # ---------------- 渲染 ----------------
    def _draw_card(self) -> None:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 2 or h <= 2:
            return
        self.canvas.delete("shape")
        self.canvas.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(16)),
                                   fill=theme.CARD, outline=theme.LINE, width=1, tags="shape")
        self.canvas.tag_lower("shape")

    def refresh(self) -> None:
        items = self.ctl.data.desktop_countdowns()
        self._items = len(items)
        for child in self.rows.winfo_children():
            child.destroy()

        if not items:
            self.withdraw()
            return
        self.deiconify()
        self.head.configure(text="倒计时" if len(items) == 1 else f"倒计时 · {len(items)} 个")

        day_font = tkfont.Font(family=theme.family(), size=-theme.S(40), weight="bold")
        name_font = tkfont.Font(family=theme.family(), size=-theme.S(12))
        unit_font = tkfont.Font(family=theme.family(), size=-theme.S(12), weight="bold")

        for i, cd in enumerate(items):
            if i:
                tk.Frame(self.rows, bg=theme.LINE, height=1).pack(fill="x", pady=theme.S(6))
            row = tk.Frame(self.rows, bg=theme.CARD)
            row.pack(fill="x")
            tk.Label(row, text=cd.name, bg=theme.CARD, fg=theme.FG2, font=name_font,
                     anchor="w").pack(fill="x")

            bottom = tk.Frame(row, bg=theme.CARD)
            bottom.pack(fill="x")
            n = cd.days_left()
            if n is None:
                big, unit = "—", ""
            elif n > 0:
                big, unit = str(n), "天"
            elif n == 0:
                big, unit = "今天", ""
            else:
                big, unit = str(abs(n)), "天前"
            tk.Label(bottom, text=big, bg=theme.CARD, fg=theme.FG, font=day_font,
                     anchor="w").grid(row=0, column=0, sticky="sw")
            if unit:
                tk.Label(bottom, text=unit, bg=theme.CARD, fg=theme.FG3, font=unit_font,
                         anchor="sw").grid(row=0, column=1, sticky="sw",
                                           padx=(theme.S(5), 0), pady=(0, theme.S(10)))
            for w in (row, bottom, *row.winfo_children(), *bottom.winfo_children()):
                self._bind_drag(w)

        # 宽度按内容自适应，避免大数字把「天」挤出窗口；
        # 下限给到 186 是为了让头部「倒计时」与「永恒」之间留出呼吸位。
        self.update_idletasks()
        pad = self._pad
        need_w = max(theme.S(186), self.shell.winfo_reqwidth() + pad * 2)
        need_h = max(theme.S(60), self.shell.winfo_reqheight() + pad * 2)
        if self.winfo_width() != need_w or self.winfo_height() != need_h:
            self.geometry(f"{need_w}x{need_h}")
        self.canvas.itemconfigure(self._win, width=need_w - pad * 2, height=need_h - pad * 2)
        self.after_idle(self._draw_card)

    def _tick(self) -> None:
        try:
            # Win+D / 显示桌面 会把普通窗口最小化，这里让它自己回来，
            # 观感上等同「贴在桌面上」。
            if self._hwnd and win32util.is_minimized(self._hwnd):
                win32util.restore_no_activate(self._hwnd)
                self._move_to(*self._last_xy)
            if not self._drag:            # 拖动过程中不要重建控件
                self.refresh()
        except Exception:
            pass
        self._job = self.after(3000, self._tick)

    def destroy(self) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        super().destroy()
