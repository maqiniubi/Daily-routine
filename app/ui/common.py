"""通用 UI：ttk 深色化样式、表单对话框、确认框、下拉选择器、滚动容器。

改版要点：
- ttk 控件（表格 / 输入框 / 数字框）统一成「无边框 + 卡片底 + 蓝色选中」；
- 按钮换成自绘圆角按钮（widgets.Button），保证和卡片同一套圆角语言；
- 下拉选择器仍是 tk.Frame（兼容既有调用），内部用 Canvas 画胶囊 + 文本。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import theme, win32util
from .widgets import Button, RoundedBox


def init_style(root, groups: tuple[str, ...] = ("form", "table")) -> None:
    """统一深色主题样式（Apple 层级配色）。

    groups 用来按需刷新：
    - "form"：按钮 / 输入框 / 标签等表单类样式；
    - "table"：Treeview 表格样式。

    换配色时只刷 "form"：表格样式一改，3 个 Treeview 会全部重新派生
    （实测 24 ms 的空耗），而表格页看不见时这笔钱不该花——
    等切到那一页再补刷（见 MainWindow._flush_pending_restyle）。

    另外两处「只做一次」的操作：
    - ``style.theme_use("clam")`` 会把整个 ttk 主题重新套一遍，逼所有 ttk 控件
      重新派生选项并重排；
    - ``style.layout("Treeview", ...)`` 会让每个表格重建布局。
    换配色只需要改颜色，所以这两步只在第一次做。
    """
    style = ttk.Style(root)
    try:
        if style.theme_use() != "clam":       # 换配色时不必重套主题
            style.theme_use("clam")
    except Exception:
        pass

    style.configure(
        ".",
        background=theme.BG,
        foreground=theme.FG,
        fieldbackground=theme.CARD,
        bordercolor=theme.LINE,
        lightcolor=theme.LINE,
        darkcolor=theme.LINE,
        troughcolor=theme.SURFACE,
        focuscolor=theme.ACCENT,
        selectbackground=theme.ACCENT,
        selectforeground=theme.ON_ACCENT,
    )
    style.configure("TFrame", background=theme.BG)
    style.configure("Card.TFrame", background=theme.CARD)
    style.configure("TLabel", background=theme.BG, foreground=theme.FG, font=theme.T("body"))
    style.configure("Muted.TLabel", background=theme.BG, foreground=theme.FG2, font=theme.T("subhead"))
    style.configure("H1.TLabel", background=theme.BG, foreground=theme.FG, font=theme.T("title"))
    style.configure("Card.TLabel", background=theme.CARD, foreground=theme.FG, font=theme.T("body"))

    style.configure("TButton", background=theme.CARD_HOVER, foreground=theme.FG, borderwidth=0,
                    focusthickness=0, padding=(theme.S(12), theme.S(6)), font=theme.T("body"))
    style.map("TButton", background=[("active", theme.FILL), ("pressed", theme.FILL),
                                     ("disabled", theme.SURFACE)],
              foreground=[("disabled", theme.FG3)])
    style.configure("Primary.TButton", background=theme.FG, foreground=theme.BG, font=theme.T("body-bold"))
    style.map("Primary.TButton", background=[("active", "#dcdce2"), ("pressed", "#c4c4cb")],
              foreground=[("active", theme.BG)])
    style.configure("Ghost.TButton", background=theme.BG, foreground=theme.FG2)
    style.map("Ghost.TButton", background=[("active", theme.CARD_HOVER)], foreground=[("active", theme.FG)])

    # ---- 表格 ----
    if "table" in groups:
        style.configure("Treeview", background=theme.CARD, fieldbackground=theme.CARD,
                        foreground=theme.FG, borderwidth=0, rowheight=theme.S(30),
                        font=theme.T("body"))
        style.configure("Treeview.Heading", background=theme.CARD, foreground=theme.FG2,
                        borderwidth=0, relief="flat", font=theme.T("caption"),
                        padding=(theme.S(2), theme.S(8)))
        style.map("Treeview.Heading", background=[("active", theme.CARD)],
                  foreground=[("active", theme.FG)])
        style.map("Treeview", background=[("selected", theme.ACCENT)],
                  foreground=[("selected", theme.ON_ACCENT)])
        try:
            if style.layout("Treeview") != [("Treeview.treearea", {"sticky": "nswe"})]:
                style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])   # 去掉外框
        except Exception:
            pass

    # ---- 输入 ----
    style.configure("TEntry", fieldbackground=theme.CARD_HOVER, foreground=theme.FG,
                    insertcolor=theme.FG, bordercolor=theme.LINE, lightcolor=theme.LINE,
                    darkcolor=theme.LINE, padding=(theme.S(9), theme.S(7)), font=theme.T("body"),
                    borderwidth=0, relief="flat")
    style.map("TEntry", bordercolor=[("focus", theme.ACCENT)],
              lightcolor=[("focus", theme.ACCENT)], darkcolor=[("focus", theme.ACCENT)],
              fieldbackground=[("disabled", theme.CARD)], foreground=[("disabled", theme.FG3)])

    style.configure("TCombobox", fieldbackground=theme.CARD_HOVER, background=theme.CARD_HOVER,
                    foreground=theme.FG, arrowcolor=theme.FG2, borderwidth=0,
                    bordercolor=theme.LINE, padding=(theme.S(9), theme.S(6)), font=theme.T("body"))
    style.map("TCombobox",
              fieldbackground=[("readonly", theme.CARD_HOVER)],
              foreground=[("readonly", theme.FG)],
              selectbackground=[("readonly", theme.CARD_HOVER)],
              selectforeground=[("readonly", theme.FG)],
              bordercolor=[("focus", theme.ACCENT)])
    style.configure("TSpinbox", fieldbackground=theme.CARD_HOVER, foreground=theme.FG,
                    arrowcolor=theme.FG2, borderwidth=0, bordercolor=theme.LINE,
                    padding=(theme.S(7), theme.S(5)), font=theme.T("body"))
    style.map("TSpinbox", bordercolor=[("focus", theme.ACCENT)])
    style.configure("TCheckbutton", background=theme.CARD, foreground=theme.FG, font=theme.T("body"))
    style.map("TCheckbutton", background=[("active", theme.CARD)])
    style.configure("TSeparator", background=theme.LINE)
    style.configure("TScale", background=theme.BG, troughcolor=theme.CARD_HOVER)

    # ---- 滚动条：去掉上下箭头，只留圆角滑块（和自绘滚动条同一套语言）----
    style.layout("Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
        ]}),
    ])
    style.layout("Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"sticky": "ew", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
        ]}),
    ])
    style.configure("Vertical.TScrollbar", background=theme.SCROLL, troughcolor=theme.CARD,
                    bordercolor=theme.CARD, lightcolor=theme.SCROLL, darkcolor=theme.SCROLL,
                    arrowcolor=theme.CARD, arrowsize=1, width=theme.S(8),
                    relief="flat", borderwidth=0)
    style.map("Vertical.TScrollbar",
              background=[("active", theme.SCROLL_HOVER), ("pressed", theme.SCROLL_HOVER)],
              lightcolor=[("active", theme.SCROLL_HOVER)],
              darkcolor=[("active", theme.SCROLL_HOVER)])
    style.configure("Horizontal.TScrollbar", background=theme.SCROLL, troughcolor=theme.CARD,
                    bordercolor=theme.CARD, lightcolor=theme.SCROLL, darkcolor=theme.SCROLL,
                    arrowsize=1, width=theme.S(8), relief="flat", borderwidth=0)

    root.option_add("*TCombobox*Listbox.background", theme.CARD_HOVER)
    root.option_add("*TCombobox*Listbox.foreground", theme.FG)
    root.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", theme.ON_ACCENT)
    root.option_add("*TCombobox*Listbox.font", theme.T("body"))


def bar_bottom() -> int:
    """顶部悬浮条的底边（像素）。弹窗一律排在它下面，别被玻璃条压住。

    悬浮条高度是可调的（course_area_h），所以不能再写死经验值——
    从根窗口身上取控制器，实时问它当前条高。
    """
    root = getattr(tk, "_default_root", None)
    ctl = getattr(root, "_ctl", None) if root is not None else None
    try:
        return int(ctl.topbar.height()) + theme.S(6)
    except Exception:
        return theme.S(150)


def center(window, parent=None, width: int | None = None, height: int | None = None) -> None:
    window.update_idletasks()
    w = width or window.winfo_width()
    h = height or window.winfo_height()
    if parent is not None and parent.winfo_exists() and parent.winfo_viewable():
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        x = px + max(0, (pw - w) // 2)
        y = py + max(0, (ph - h) // 3)
    else:
        x = (window.winfo_screenwidth() - w) // 2
        y = (window.winfo_screenheight() - h) // 3
    # 父窗口若是悬浮条（贴顶且很扁），按比例居中会算到屏幕外或被条压住，
    # 统一兜一道：任何弹窗都不许压在顶部悬浮条上。
    y = max(y, bar_bottom())
    window.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


def _show_dialog(window: tk.Toplevel) -> None:
    """统一收尾：置顶、深色标题栏、居中、模态。"""
    window.update_idletasks()
    win32util.set_dark_titlebar(win32util.hwnd_of(window))
    window.lift()
    window.focus_force()


class FormDialog(tk.Toplevel):
    """通用表单对话框。字段：key/label/kind(entry|combo)/options/default。"""

    def __init__(self, parent, title: str, fields: list[dict], values: dict | None = None,
                 on_submit=None, hint: str = "", width: int | None = None):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(parent)
        self._on_submit = on_submit
        self.result: dict | None = None
        self._vars: dict[str, tk.Variable] = {}

        body = tk.Frame(self, bg=theme.BG, padx=theme.P(6), pady=theme.P(5))
        body.pack(fill="both", expand=True)

        tk.Label(body, text=title, bg=theme.BG, fg=theme.FG, font=theme.T("title"),
                 anchor="w").pack(fill="x")
        if hint:
            tk.Label(body, text=hint, bg=theme.BG, fg=theme.FG3, font=theme.T("caption"),
                     anchor="w", justify="left", wraplength=theme.S(360)).pack(
                fill="x", pady=(theme.S(6), 0))

        form = tk.Frame(body, bg=theme.BG)
        form.pack(fill="x", pady=(theme.P(4), 0))
        form.columnconfigure(1, weight=1)

        values = values or {}
        for row, f in enumerate(fields):
            tk.Label(form, text=f["label"], bg=theme.BG, fg=theme.FG2, font=theme.T("subhead"),
                     anchor="w").grid(row=row, column=0, sticky="w", pady=theme.S(6),
                                      padx=(0, theme.P(4)))
            key = f["key"]
            default = values.get(key, f.get("default", ""))
            if f.get("kind") == "combo":
                var = tk.StringVar(value=str(default))
                widget = ttk.Combobox(form, textvariable=var, values=f.get("options", []),
                                      state="readonly", width=22)
            else:
                var = tk.StringVar(value=str(default))
                widget = ttk.Entry(form, textvariable=var, width=24)
            widget.grid(row=row, column=1, sticky="ew", pady=theme.S(6))
            self._vars[key] = var

        self._error = tk.Label(body, text="", bg=theme.BG, fg=theme.DANGER, font=theme.T("caption"),
                               anchor="w", justify="left", wraplength=theme.S(360))
        self._error.pack(fill="x", pady=(theme.S(4), 0))

        btns = tk.Frame(body, bg=theme.BG)
        btns.pack(fill="x", pady=(theme.P(5), 0))
        Button(btns, "保存", self._submit, kind="primary").pack(side="right")
        Button(btns, "取消", self.destroy, kind="ghost").pack(side="right", padx=(0, theme.S(6)))

        self.bind("<Return>", lambda e: self._submit())
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        center(self, parent, width=width or body.winfo_reqwidth() + theme.S(12),
               height=body.winfo_reqheight() + theme.S(4))
        self.deiconify()
        _show_dialog(self)
        self.grab_set()
        if self._vars:
            self.after(50, self.focus_force)

    def _submit(self) -> None:
        data = {k: v.get().strip() if isinstance(v, tk.StringVar) else v for k, v in self._vars.items()}
        if self._on_submit:
            try:
                self._on_submit(data)
            except ValueError as exc:
                self._error.configure(text=str(exc))
                return
        self.result = data
        self.destroy()


def ask_yes_no(parent, title: str, message: str) -> bool:
    return _MessageBox(parent, title, message, yes_no=True).result


def show_info(parent, title: str, message: str) -> None:
    _MessageBox(parent, title, message, yes_no=False)


class _MessageBox(tk.Toplevel):
    def __init__(self, parent, title: str, message: str, yes_no: bool):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.result = False
        # 父窗口不可见（例如只剩悬浮条时被 withdraw 的根窗口）时绝不能 transient，
        # 否则系统会把对话框藏到隐藏父窗口的 z-order 里，表现为「点了没反应」。
        parent_visible = parent is not None and parent.winfo_exists() and parent.winfo_viewable()
        if parent_visible:
            self.transient(parent)

        body = tk.Frame(self, bg=theme.BG, padx=theme.P(6), pady=theme.P(5))
        body.pack(fill="both", expand=True)
        tk.Label(body, text=title, bg=theme.BG, fg=theme.FG, font=theme.T("headline"),
                 anchor="w").pack(fill="x")
        tk.Label(body, text=message, bg=theme.BG, fg=theme.FG2, font=theme.T("body"), anchor="w",
                 justify="left", wraplength=theme.S(380)).pack(
            fill="x", pady=(theme.P(2), theme.P(5)))
        btns = tk.Frame(body, bg=theme.BG)
        btns.pack(fill="x")
        if yes_no:
            Button(btns, "确定", lambda: (setattr(self, "result", True), self.destroy()),
                   kind="primary").pack(side="right")
            Button(btns, "取消", self.destroy, kind="ghost").pack(side="right", padx=(0, theme.S(6)))
        else:
            Button(btns, "知道了", self.destroy, kind="primary").pack(side="right")

        self.bind("<Escape>", lambda e: self.destroy())
        self.update_idletasks()
        self._place(body.winfo_reqwidth() + theme.S(10),
                    body.winfo_reqheight() + theme.S(4),
                    parent if parent_visible else None)
        self.deiconify()
        self.attributes("-topmost", True)          # 必须盖在顶部悬浮条之上
        win32util.set_dark_titlebar(win32util.hwnd_of(self))
        self.lift()
        self.focus_force()
        try:
            self.grab_set()
        except tk.TclError:
            pass                                   # 不可见时不能 grab，否则模态失效
        self.wait_window()

    def _place(self, w: int, h: int, parent) -> None:
        """居中显示，并保证不被顶部悬浮条遮挡。"""
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if parent is not None:
            x = parent.winfo_rootx() + max(0, (parent.winfo_width() - w) // 2)
            y = parent.winfo_rooty() + max(0, (parent.winfo_height() - h) // 3)
        else:
            x = (sw - w) // 2
            y = (sh - h) // 3
        y = max(bar_bottom(), y)                   # 按当前条高动态避让
        y = min(y, max(theme.S(40), sh - h - theme.S(40)))
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


class _PillSelect(tk.Frame):
    """胶囊下拉：Canvas 自绘圆角底 + 文本 + 箭头，点击弹原生菜单。"""

    def __init__(self, parent, var: tk.StringVar, values_provider, on_pick,
                 *, bg: str | None = None, fill: str | None = None,
                 width_px: int | None = None, height: float = 32):
        bg = bg or parent.cget("bg")
        super().__init__(parent, bg=bg, width=width_px or theme.S(196),
                         height=theme.S(height))
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._var = var
        self._provider = values_provider
        self._on_pick = on_pick
        self._bg = bg
        self._fill = fill or theme.CARD_HOVER
        self._hover = False
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw())
        self.canvas.bind("<Enter>", lambda e: self._set_hover(True))
        self.canvas.bind("<Leave>", lambda e: self._set_hover(False))
        self.canvas.bind("<Button-1>", self._popup)
        var.trace_add("write", lambda *_: self._draw())

    def _set_hover(self, on: bool) -> None:
        self._hover = on
        self._draw()

    def _draw(self) -> None:
        from .widgets import rounded_points

        cv = self.canvas
        w, h = cv.winfo_width(), cv.winfo_height()
        if w <= 2 or h <= 2:
            return
        cv.delete("all")
        fill = theme.mix(self._fill, theme.FG, 0.06) if self._hover else self._fill
        cv.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(8)),
                          fill=fill, outline=theme.LINE, width=1)
        cv.create_text(theme.S(11), h / 2, text=self._var.get(), fill=theme.FG,
                       font=theme.T("body"), anchor="w")
        cv.create_text(w - theme.S(11), h / 2 - theme.S(1), text="⌄", fill=theme.FG3,
                       font=theme.T("body"), anchor="e")

    def _popup(self, _e=None) -> None:
        menu = tk.Menu(self, tearoff=0, bg=theme.CARD_HOVER, fg=theme.FG,
                       activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT,
                       bd=0, font=theme.T("body"), activeborderwidth=0)
        for item in self._provider():
            menu.add_command(label=item, command=lambda i=item: self._choose(i))
        try:
            menu.tk_popup(self.winfo_rootx(), self.winfo_rooty() + self.winfo_height() + theme.S(2))
        finally:
            menu.grab_release()

    def _choose(self, value: str) -> None:
        self._var.set(value)
        self._on_pick(value)


def option_menu(parent, var: tk.StringVar, values_provider, on_pick, bg: str | None = None,
                width_px: int | None = None, fill: str | None = None) -> tk.Frame:
    """深色胶囊下拉选择器（返回 tk.Frame，便于 grid/pack）。"""
    return _PillSelect(parent, var, values_provider, on_pick, bg=bg, fill=fill,
                       width_px=width_px)


class ScrollFrame(tk.Frame):
    """深色垂直滚动容器：内容放得下时自动隐藏滚动条，超出时显示自绘细滚动条。

    用法：sc = ScrollFrame(parent); 往 sc.body 里 pack 内容。
    """

    BAR_W = 6          # 滚动条逻辑宽度
    MIN_THUMB = 26     # 滑块最小高度

    def __init__(self, parent, bg: str | None = None):
        self._bg = bg or theme.BG
        super().__init__(parent, bg=self._bg)
        self.canvas = tk.Canvas(self, bg=self._bg, highlightthickness=0, bd=0,
                                yscrollincrement=theme.S(20))
        self.canvas.pack(side="left", fill="both", expand=True)

        self.bar = tk.Canvas(self, width=theme.S(self.BAR_W), bg=self._bg,
                             highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.configure(yscrollcommand=self._on_scroll_set)

        self.body = tk.Frame(self.canvas, bg=self._bg)
        self._item = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self._bar_shown = False
        self._first, self._last = 0.0, 1.0
        self._drag: tuple[int, float] | None = None
        self._hover = False
        self._sync_job = None

        self.body.bind("<Configure>", self._sync_region)
        self.canvas.bind("<Configure>", self._sync_width)

        self.bar.bind("<Button-1>", self._bar_press)
        self.bar.bind("<B1-Motion>", self._bar_move)
        self.bar.bind("<ButtonRelease-1>", self._bar_release)
        self.bar.bind("<Enter>", lambda e: self._set_hover(True))
        self.bar.bind("<Leave>", lambda e: self._set_hover(False))
        self.bar.bind("<Configure>", lambda e: self._draw_bar())

        # 常驻滚轮监听，命中判断交给 _wheel（避免多容器互相抢绑）
        self.canvas.bind_all("<MouseWheel>", self._wheel, add="+")

        # 首次布局时 canvas 高度还是 1，会误判成「内容超高」；等布局稳定再复核一次
        self.after(80, self._refresh_bar)

    # ---------------- 内部 ----------------
    def restyle(self) -> None:
        """换配色后重铺底色（画布与滑块都是自绘的，得显式重画）。"""
        self._bg = theme.remap(self._bg, "bg")
        try:
            self.configure(bg=self._bg)
            self.canvas.configure(bg=self._bg)
            self.bar.configure(bg=self._bg)
        except tk.TclError:
            return
        self._draw_bar()

    def _sync_region(self, _event=None) -> None:
        """滚动区重算：合并成一次。

        换一次配色，页面里几十个控件一起重排，<Configure> 会连着来几十次；
        每次都重算一遍滚动区 + 重画滑块纯属浪费（实测能吃掉几十毫秒）。
        用 after_idle 合并成一次即可。
        """
        if self._sync_job is not None:
            try:
                self.after_cancel(self._sync_job)
            except tk.TclError:
                pass
        self._sync_job = self.after_idle(self._do_sync_region)

    def _do_sync_region(self) -> None:
        self._sync_job = None
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._refresh_bar()

    def _sync_width(self, event) -> None:
        self.canvas.itemconfigure(self._item, width=event.width)
        self._sync_region()

    def _on_scroll_set(self, first: str, last: str) -> None:
        self._first, self._last = float(first), float(last)
        self._draw_bar()
        self._refresh_bar()

    def _refresh_bar(self) -> None:
        # 容差 6px：底部留白造成的一点点溢出不值得弹滚动条，否则满屏都是假滚动条
        has_more = self.body.winfo_reqheight() > self.canvas.winfo_height() + theme.S(6)
        if has_more and not self._bar_shown:
            self.bar.pack(side="right", fill="y", padx=(theme.S(3), 0))
            self._bar_shown = True
        elif not has_more and self._bar_shown:
            self.bar.pack_forget()
            self._bar_shown = False
            if self.canvas.yview()[0] > 0:
                self.canvas.yview_moveto(0)
        if self._bar_shown:
            self._draw_bar()

    def _thumb(self) -> tuple[int, int]:
        h = self.bar.winfo_height() or theme.S(100)
        span = max(0.0, min(1.0, self._last - self._first))
        th = max(theme.S(self.MIN_THUMB), h * span)
        y0 = (h - th) * (self._first / (1.0 - span) if span < 1.0 else 0.0)
        return int(y0), int(y0 + th)

    def _draw_bar(self) -> None:
        from .widgets import rounded_points

        if not self._bar_shown:
            return
        self.bar.delete("all")
        w = self.bar.winfo_width() or theme.S(self.BAR_W)
        x0, x1 = theme.S(1), w - theme.S(1)
        y0, y1 = self._thumb()
        self.bar.create_polygon(rounded_points(x0, y0, x1, y1, (x1 - x0) / 2),
                                fill=theme.SCROLL_HOVER if self._hover or self._drag else theme.SCROLL,
                                outline="")

    def _set_hover(self, on: bool) -> None:
        self._hover = on
        self._draw_bar()

    def _inside(self, widget) -> bool:
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _wheel(self, event) -> None:
        if not self._bar_shown:
            return
        if not self._inside(self.winfo_containing(event.x_root, event.y_root)):
            return
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _bar_press(self, event) -> None:
        y0, y1 = self._thumb()
        if y0 <= event.y <= y1:
            self._drag = (event.y, self._first)
        else:
            h = self.bar.winfo_height() or 1
            span = self._last - self._first
            target = event.y / h - span / 2
            self.canvas.yview_moveto(max(0.0, min(1.0 - span, target)))
        self._draw_bar()

    def _bar_move(self, event) -> None:
        if self._drag is None:
            return
        y, first = self._drag
        h = self.bar.winfo_height() or 1
        span = self._last - self._first
        self.canvas.yview_moveto(max(0.0, min(1.0 - span, first + (event.y - y) / h)))

    def _bar_release(self, _event=None) -> None:
        self._drag = None
        self._draw_bar()

    # ---------------- 对外 ----------------
    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def scroll_to_bottom(self) -> None:
        self.update_idletasks()
        self._sync_region()
        self.canvas.yview_moveto(1.0)

    def scroll_to_widget(self, widget) -> None:
        """把某个子控件滚动到可视区中部附近（用于定位当前星期）。"""
        self.update_idletasks()
        self._sync_region()
        self.update_idletasks()
        total = self.body.winfo_reqheight() or 1
        view = self.canvas.winfo_height() or total
        if total <= view + 1:
            return
        top = widget.winfo_rooty() - self.body.winfo_rooty()   # 换算到 body 坐标系
        self.canvas.yview_moveto(max(0.0, min(1.0, (top - view * 0.35) / total)))
