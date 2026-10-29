"""外观自定义页：配色预设 + 锚点色微调 + 不透明度 + 实时预览。

设计要点：
- **实时**：任何一次取色/失焦校验成功都立刻写回 settings 并下发到 theme，
  悬浮条整条重建、设置中心就地重着色（不销毁窗口，避免正在操作的控件消失）。
- **不会调崩**：用户只选 5 + 4 个锚点色，层级色（hover / fill / 三级文字 / 网格线）
  由 theme.apply_palette 按锚点推导，所以「卡片比背景还暗」这类组合根本产生不了。
- **预览是真的**：预览图画的是当前 theme 令牌而不是另抄一份配色，
  改完色之后预览不能比真界面更「好看」。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, ttk

from .. import palette, theme
from .common import ScrollFrame, ask_yes_no
from .widgets import Button, RoundedBox, rounded_points

#: 预览画布的基准尺寸（dp）
_PREVIEW_W = 330
_PREVIEW_H = 236

#: 壁纸渐变色：给半透明条一个「有内容可透」的背景，纯色背景看不出透明度
_WALL_A = "#2b3f74"
_WALL_B = "#8a4a72"

_UI_LABELS = (("bg", "背景色"), ("card", "卡片色"), ("fg", "文字色"),
              ("line", "边框色"), ("accent", "强调色"))
_BAR_LABELS = (("bg", "背景色"), ("fg", "文字色"), ("line", "描边色"),
               ("accent", "强调色"))


class Swatch(tk.Canvas):
    """一枚可点的颜色方块：点开系统取色器。"""

    def __init__(self, parent, color: str, on_click, bg: str | None = None,
                 width: float = 44, height: float = 21):
        self._bg = bg or parent.cget("bg")
        self._color = color
        self._on_click = on_click
        # 注意：不能用 self._w / self._h —— Misc._w 是控件路径名，会被覆盖成字符串
        self._cw, self._ch = theme.S(width), theme.S(height)
        super().__init__(parent, width=self._cw, height=self._ch, bg=self._bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", lambda e: self._on_click())
        self.bind("<Configure>", lambda e: self._draw())
        self.after_idle(self._draw)

    def set_color(self, color: str) -> None:
        self._color = color
        self._draw()

    def _draw(self) -> None:
        w, h = self._cw, self._ch
        self.delete("all")
        # 外圈用「比色块更极端的明暗」描一下，浅色块贴在白卡上也能看出边界
        edge = theme.mix(self._color, "#000000" if theme.lum(self._color) > 0.55 else "#ffffff", 0.28)
        self.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(5)),
                            fill=self._color, outline=edge, width=1)

    def restyle(self) -> None:
        self._bg = theme.remap(self._bg, "bg")
        try:
            self.configure(bg=self._bg)
        except tk.TclError:
            return
        self._draw()


class ColorRow(tk.Frame):
    """一行：名称 + 色块 + #rrggbb 输入框。

    输入框只在回车/失焦时校验，边打字边纠正会一直跳字（和关机时间同一个坑）。
    """

    def __init__(self, parent, title: str, color: str, on_change, bg: str | None = None):
        bg = bg or parent.cget("bg")
        super().__init__(parent, bg=bg)
        self._on_change = on_change
        self._color = color
        self._var = tk.StringVar(value=color)

        tk.Label(self, text=title, bg=bg, fg=theme.FG, font=theme.T("body"),
                 anchor="w").pack(side="left", fill="x", expand=True)
        self._entry = ttk.Entry(self, textvariable=self._var, width=8, justify="center",
                                font=theme.T("body"))
        self._entry.pack(side="right")
        self._entry.bind("<Return>", self._commit)
        self._entry.bind("<FocusOut>", self._commit)
        self.swatch = Swatch(self, color, self._pick, bg=bg)
        self.swatch.pack(side="right", padx=(0, theme.S(6)))

    # ---------- 对外 ----------
    def set_color(self, color: str) -> None:
        self._color = color
        self._var.set(color)
        self.swatch.set_color(color)

    # ---------- 内部 ----------
    def _commit(self, _event=None) -> None:
        fixed = palette.normalize(self._var.get())
        if fixed is None or fixed == self._color:
            self._var.set(self._color)          # 非法输入直接退回原值
            return
        self._on_change(fixed)

    def _pick(self) -> None:
        _rgb, hexcolor = colorchooser.askcolor(color=self._color, parent=self.winfo_toplevel(),
                                               title="选择颜色")
        if hexcolor:
            fixed = palette.normalize(hexcolor)
            if fixed:
                self._on_change(fixed)


class Preview(tk.Canvas):
    """实时预览：一张「桌面壁纸 + 悬浮条 + 设置中心」的小样。

    画的是**当前 theme 令牌**，不是另抄的配色表——改完色之后预览与真界面一致。
    """

    def __init__(self, parent, ctl, bg: str | None = None):
        self._ctl = ctl
        self._bg = bg or parent.cget("bg")
        self._pw, self._ph = theme.S(_PREVIEW_W), theme.S(_PREVIEW_H)
        super().__init__(parent, width=self._pw, height=self._ph, bg=self._bg,
                         highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self.redraw())
        self.after_idle(self.redraw)

    def restyle(self) -> None:
        self._bg = theme.remap(self._bg, "bg")
        try:
            self.configure(bg=self._bg)
        except tk.TclError:
            return
        self.redraw()

    # ---------- 绘制 ----------
    def redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        if w <= 4:
            w = self._pw
        # 尺寸固定按 1dp = scale 像素画，多出来的宽度只用来铺壁纸，小样居中——
        # 等比拉伸会把字号和圆角一起放大，看着像「放大的截图」而不是「缩略图」。
        u = theme.scale()
        DW, DH = _PREVIEW_W * u, _PREVIEW_H * u      # 小样自身的尺寸（不含居中留白）
        H = max(self.winfo_height() if self.winfo_height() > 4 else self._ph, int(DH))
        ox = max(0.0, (w - DW) / 2)

        def X(v: float) -> float:
            # 只做缩放，不掺横向偏移：偏移统一在画完之后整组平移，
            # 否则圆角半径、宽度里也会被加进偏移量，圆角会变成巨大的椭圆。
            return v * u

        self._wallpaper(w, H)
        wall_ids = set(self.find_all())

        # 悬浮条（压在壁纸上，用 alpha 与壁纸混色 —— 这就是「通透度」的观感）
        ui_alpha, bar_alpha = palette.alphas(self._ctl.data.settings)
        face = theme.mix(_WALL_A, theme.GLASS, bar_alpha)
        bx0, by0, bx1 = X(6), X(5), X(_PREVIEW_W - 6)
        by1 = by0 + X(46)
        self.create_polygon(rounded_points(bx0, by0, bx1, by1, X(11)),
                            fill=face, outline=theme.BAR_LINE, width=1)
        self.create_line(bx0 + X(10), by0 + 1.2, bx1 - X(10), by0 + 1.2,
                         fill=theme.mix(theme.GLASS, "#ffffff", 0.22))
        self.create_text(bx0 + X(11), by0 + X(11), text="09月01日  周一", anchor="w",
                         fill=theme.BAR_FG, font=theme.F(8, True))
        self.create_text(bx1 - X(11), by0 + X(11), text="09:50:07", anchor="e",
                         fill=theme.BAR_FG, font=theme.F(9, True))
        self.create_text(bx0 + X(11), by0 + X(23), text="正在上课 · 数学", anchor="w",
                         fill=theme.BAR_FG2, font=theme.F(7))

        # 24h 进度条
        py = by0 + X(32)
        self.create_line(bx0 + X(10), py, bx1 - X(10), py,
                         fill=theme.BAR_TRACK, width=max(2, int(X(3))))
        self.create_line(bx0 + X(10), py, bx0 + X(10) + (bx1 - bx0 - X(20)) * 0.66, py,
                         fill=theme.BAR_FG, width=max(2, int(X(3))))
        self.create_oval(bx0 + X(10) + (bx1 - bx0 - X(20)) * 0.66 - X(1.6), py - X(1.6),
                         bx0 + X(10) + (bx1 - bx0 - X(20)) * 0.66 + X(1.6), py + X(1.6),
                         fill=theme.BAR_FG, outline=theme.GLASS, width=1)
        # 今日时段条
        sy0, sy1 = by0 + X(37), by0 + X(44)
        cursor = bx0 + X(10)
        for start, end, is_class in ((0.02, 0.18, False), (0.18, 0.34, True), (0.35, 0.53, True),
                                     (0.54, 0.63, False), (0.63, 0.85, True)):
            sx = bx0 + X(10) + (bx1 - bx0 - X(20)) * start
            ex = bx0 + X(10) + (bx1 - bx0 - X(20)) * end
            fill = theme.BAR_FG if is_class else theme.mix(theme.GLASS, theme.BAR_LINE, 0.22)
            self.create_polygon(rounded_points(sx, sy0, ex - 1, sy1, X(2.5)),
                                fill=fill, outline="" if is_class else theme.BAR_TICK, width=1)
            if is_class:
                cursor = max(cursor, sx)
        self.create_line(cursor + X(4), sy0 - X(1.5), cursor + X(4), sy1 + X(1.5),
                         fill=theme.BAR_ACCENT, width=1.5)

        # 设置中心小样
        wx0, wy0, wx1 = X(14), X(58), X(_PREVIEW_W - 14)
        wy1 = H - X(6)
        win_face = theme.mix(_WALL_B, theme.BG, ui_alpha)
        self.create_polygon(rounded_points(wx0, wy0, wx1, wy1, X(10)),
                            fill=win_face, outline=theme.LINE, width=1)
        self.create_text(wx0 + X(11), wy0 + X(11), text="班级作息助手", anchor="w",
                         fill=theme.FG, font=theme.F(9, True))
        self.create_text(wx1 - X(11), wy0 + X(11), text="设置中心", anchor="e",
                         fill=theme.FG3, font=theme.F(7))

        # 分段导航
        tx, ty = wx0 + X(10), wy0 + X(24)
        track_w = (wx1 - wx0) - X(20)
        self.create_polygon(rounded_points(tx, ty, tx + track_w, ty + X(15), X(7.5)),
                            fill=theme.mix(win_face, theme.SURFACE, 0.85),
                            outline=theme.LINE, width=1)
        labels = ("作息", "每周", "课程", "倒计时")
        seg = track_w / len(labels)
        self.create_polygon(rounded_points(tx + X(2), ty + X(2), tx + seg - X(2), ty + X(13), X(5.5)),
                            fill=theme.PILL, outline=theme.mix(theme.PILL, theme.FG, 0.14), width=1)
        for i, text in enumerate(labels):
            self.create_text(tx + seg * (i + 0.5), ty + X(7.5), text=text,
                             fill=theme.FG if i == 0 else theme.FG2, font=theme.F(7))

        # 两张卡片
        card_top = ty + X(21)
        for col, (head, sub) in enumerate((("时段提醒", "到达作息节点时弹出提醒"),
                                           ("桌面悬浮条", "显示今日时段条"))):
            cx0 = wx0 + X(10) + col * (track_w / 2 + X(2))
            cx1 = cx0 + track_w / 2 - X(2)
            cy1 = card_top + X(52)
            self.create_polygon(rounded_points(cx0, card_top, cx1, cy1, X(8)),
                                fill=theme.mix(win_face, theme.CARD, 0.92),
                                outline=theme.LINE, width=1)
            self.create_text(cx0 + X(8), card_top + X(9), text=head, anchor="w",
                             fill=theme.FG3, font=theme.F(6))
            self.create_text(cx0 + X(8), card_top + X(18), text=sub, anchor="w",
                             fill=theme.FG2, font=theme.F(6))
            # 开关：开（用强调色）
            sw_x, sw_y = cx0 + X(8), card_top + X(28)
            self.create_polygon(rounded_points(sw_x, sw_y, sw_x + X(18), sw_y + X(10), X(5)),
                                fill=theme.ACCENT, outline="")
            self.create_oval(sw_x + X(9), sw_y + X(1.2), sw_x + X(16.8), sw_y + X(8.8),
                             fill="#ffffff", outline="")
            # 次要按钮
            self.create_polygon(rounded_points(sw_x + X(26), sw_y - X(1),
                                               sw_x + X(64), sw_y + X(11), X(4)),
                                fill=theme.CARD_HOVER, outline=theme.LINE, width=1)
            self.create_text(sw_x + X(45), sw_y + X(5), text="打开", fill=theme.FG,
                             font=theme.F(6))
        self.create_text(wx0 + X(11), wy1 - X(11), text="数据文件  %APPDATA%\\ClassBell",
                         anchor="w", fill=theme.FG3, font=theme.F(6))

        if ox:
            for item in self.find_all():
                if item not in wall_ids:
                    self.move(item, ox, 0)

    def _wallpaper(self, w: int, h: int) -> None:
        bands = 28
        for i in range(bands):
            t = i / (bands - 1)
            self.create_rectangle(0, h * i / bands, w, h * (i + 1) / bands + 1,
                                  fill=theme.mix(_WALL_A, _WALL_B, t), outline="")


class AppearanceTab(tk.Frame):
    @property
    def data(self):
        return self.ctl.data

    def __init__(self, parent, ctl):
        super().__init__(parent, bg=theme.BG)
        self.ctl = ctl
        self._loading = True
        self._ui = dict(palette.DEFAULT_UI)
        self._bar = dict(palette.DEFAULT_BAR)
        self._ui_rows: dict[str, ColorRow] = {}
        self._bar_rows: dict[str, ColorRow] = {}
        self._preset_buttons: list[tuple[str, Button]] = []
        self._apply_job = None

        self.scroll = ScrollFrame(self, bg=theme.BG)
        self.scroll.pack(fill="both", expand=True)

        holder = tk.Frame(self.scroll.body, bg=theme.BG)
        holder.pack(fill="x", pady=(0, theme.P(2)))
        holder.columnconfigure(0, weight=1, uniform="col")
        holder.columnconfigure(1, weight=1, uniform="col")

        left_box = RoundedBox(holder, radius=14, fill=theme.CARD, pad=0)
        left_box.grid(row=0, column=0, sticky="new", padx=(0, theme.P(3)))
        left = tk.Frame(left_box.body, bg=theme.CARD, padx=theme.P(5), pady=theme.P(2))
        left.pack(fill="both", expand=True)

        right_box = RoundedBox(holder, radius=14, fill=theme.CARD, pad=0)
        right_box.grid(row=0, column=1, sticky="new")
        right = tk.Frame(right_box.body, bg=theme.CARD, padx=theme.P(5), pady=theme.P(2))
        right.pack(fill="both", expand=True)

        # ---------- 左：预设 + 设置中心配色 ----------
        self._section(left, "配色方案")
        grid = tk.Frame(left, bg=theme.CARD)
        grid.pack(fill="x", pady=(theme.S(2), theme.S(2)))
        for i, item in enumerate(palette.PRESETS):
            btn = Button(grid, item["name"], lambda k=item["key"]: self._use_preset(k),
                         kind="secondary", height=28, bg=theme.CARD,
                         width=theme.S(92), font_role="subhead")
            btn.grid(row=i // 3, column=i % 3, sticky="ew",
                     padx=(0 if i % 3 == 0 else theme.S(4), 0),
                     pady=(0 if i < 3 else theme.S(4), 0))
            self._preset_buttons.append((item["key"], btn))
        for col in range(3):
            grid.columnconfigure(col, weight=1, uniform="p")

        self._section(left, "设置中心界面")
        for key, label in _UI_LABELS:
            row = ColorRow(left, label, self._ui[key],
                           lambda c, k=key: self._set_color("ui", k, c), bg=theme.CARD)
            row.pack(fill="x", pady=theme.S(2))
            self._ui_rows[key] = row
        self.v_ui_alpha = tk.DoubleVar(value=1.0)
        self._alpha_row(left, "窗口不透明度（0.75 ~ 1.00）", self.v_ui_alpha,
                        lambda: self._set_alpha("ui"), lo=0.75, hi=1.0)

        # ---------- 右：预览 + 悬浮条配色 ----------
        self._section(right, "实时预览")
        self.preview = Preview(right, ctl, bg=theme.CARD)
        self.preview.pack(fill="x", pady=(theme.S(2), theme.S(2)))

        self._section(right, "顶部悬浮条")
        for key, label in _BAR_LABELS:
            row = ColorRow(right, label, self._bar[key],
                           lambda c, k=key: self._set_color("bar", k, c), bg=theme.CARD)
            row.pack(fill="x", pady=theme.S(2))
            self._bar_rows[key] = row
        self.v_bar_alpha = tk.DoubleVar(value=0.86)
        self._alpha_row(right, "悬浮条通透度（0.55 ~ 1.00）", self.v_bar_alpha,
                        lambda: self._set_alpha("bar"), lo=0.55, hi=1.0)

        foot = tk.Frame(right, bg=theme.CARD)
        foot.pack(fill="x", pady=(theme.P(3), theme.S(2)))
        Button(foot, "恢复默认外观", self._reset, kind="secondary", bg=theme.CARD,
               width=theme.S(112)).pack(side="left")
        tk.Label(foot, text="只改配色，不动数据", bg=theme.CARD, fg=theme.FG3,
                 font=theme.T("caption")).pack(side="left", padx=(theme.S(8), 0))

        self._hint = tk.Label(left, text="", bg=theme.CARD, fg=theme.FG3, font=theme.T("caption"),
                              anchor="w", justify="left", wraplength=theme.S(300))
        self._hint.pack(fill="x", pady=(theme.S(3), 0))

        self._loading = False
        self.refresh()

    # ---------- 组件 ----------
    def _section(self, parent, title: str) -> None:
        holder = tk.Frame(parent, bg=theme.CARD)
        holder.pack(fill="x", pady=(theme.P(1), theme.S(1)))
        tk.Label(holder, text=title, bg=theme.CARD, fg=theme.FG2, font=theme.T("caption"),
                 anchor="w").pack(fill="x")

    def _alpha_row(self, parent, title: str, var, command, lo: float = 0.55,
                   hi: float = 1.0) -> None:
        row = tk.Frame(parent, bg=theme.CARD)
        row.pack(fill="x", pady=theme.S(2))
        tk.Label(row, text=title, bg=theme.CARD, fg=theme.FG, font=theme.T("body"),
                 anchor="w").pack(side="left", fill="x", expand=True)
        sp = ttk.Spinbox(row, from_=lo, to=hi, increment=0.02, textvariable=var, width=7,
                         command=command, format="%.2f")
        sp.pack(side="right")
        sp.bind("<FocusOut>", lambda e: command())
        sp.bind("<Return>", lambda e: command())

    # ---------- 数据 ----------
    def refresh(self) -> None:
        s = self.data.settings
        self._ui = palette.normalize_theme(s.get("ui_theme"), palette.UI_SLOTS, palette.DEFAULT_UI)
        self._bar = palette.normalize_theme(s.get("bar_theme"), palette.BAR_SLOTS, palette.DEFAULT_BAR)
        self._loading = True
        for key, row in self._ui_rows.items():
            row.set_color(self._ui[key])
        for key, row in self._bar_rows.items():
            row.set_color(self._bar[key])
        ui_alpha, bar_alpha = palette.alphas(s)
        self.v_ui_alpha.set(ui_alpha)
        self.v_bar_alpha.set(bar_alpha)
        self._loading = False
        self._mark_preset()
        self._hint.configure(
            text="· 色块可点，直接调系统取色器；也可以手填 #rrggbb 后回车。\n"
                 "· 悬停 / 填充 / 三级文字这些层级色是按锚点色自动推导的，不用逐项调。")
        self.preview.redraw()

    def _mark_preset(self) -> None:
        current = palette.match_preset(self._ui, self._bar)
        for key, btn in self._preset_buttons:
            try:
                btn.set_kind("primary" if current is not None and current["key"] == key
                             else "secondary")
            except tk.TclError:
                pass

    # ---------- 交互 ----------
    def _set_color(self, group: str, key: str, color: str) -> None:
        if self._loading:
            return
        fixed = palette.normalize(color)
        if not fixed:
            return
        s = self.data.settings
        slot = f"{group}_theme"
        theme_colors = dict(s.get(slot) or {})
        theme_colors[key] = fixed
        s[slot] = theme_colors
        if group == "ui":
            self._ui[key] = fixed
        else:
            self._bar[key] = fixed
        self._commit()

    def _set_alpha(self, which: str) -> None:
        if self._loading:
            return
        s = self.data.settings
        var = self.v_ui_alpha if which == "ui" else self.v_bar_alpha
        lo, hi = (0.75, 1.0) if which == "ui" else (0.55, 1.0)
        try:
            value = round(max(lo, min(hi, float(var.get()))), 2)
        except (TypeError, ValueError, tk.TclError):
            value = 1.0 if which == "ui" else 0.86
        var.set(value)
        s["ui_alpha" if which == "ui" else "bar_alpha"] = value
        # 透明度是连续操作（按住方向键连点），走「即时反馈 + 重活延后」
        self._commit(live=True)

    def _use_preset(self, key: str) -> None:
        item = palette.preset(key)
        if item is None:
            return
        s = self.data.settings
        s["ui_theme"] = dict(item["ui"])
        s["bar_theme"] = dict(item["bar"])
        s["ui_alpha"] = item["ui_alpha"]
        s["bar_alpha"] = item["bar_alpha"]
        self._commit()

    def _reset(self) -> None:
        if not ask_yes_no(self, "恢复默认外观",
                          "把界面与悬浮条的配色、不透明度恢复为出厂设置？\n"
                          "（作息表、课程、倒计时等数据不受影响）"):
            return
        palette.restore_defaults(self.data.settings)
        self._commit()

    # ---------- 提交 ----------
    def _commit(self, live: bool = False) -> None:
        """统一收口：落盘 → 下发主题 → 重绘自己。

        live=True 用于连续操作（拖动透明度）：只换 theme 令牌 + 重绘预览，
        十几毫秒就有反馈；悬浮条换色、设置中心重着色、ttk 样式重建这些重活
        延后到停下来之后统一做一次（见 _schedule_apply）。
        """
        if live:
            try:
                palette.apply(self.data.settings, None, ttk=False)
                self.preview.redraw()
            except Exception:
                pass
            self._schedule_apply()
            return
        self._flush_apply()          # 落盘 + 下发 + 重绘，一次做完

    def _schedule_apply(self) -> None:
        """把重活合并：连续操作期间只做最后一次。"""
        if self._apply_job is not None:
            try:
                self.after_cancel(self._apply_job)
            except tk.TclError:
                pass
        self._apply_job = self.after(160, self._flush_apply)

    def _flush_apply(self) -> None:
        if self._apply_job is not None:
            try:
                self.after_cancel(self._apply_job)
            except tk.TclError:
                pass
            self._apply_job = None
        self.ctl.save_data()
        self.ctl.apply_appearance()
        self.refresh()

    # ---------- 主题切换后的重铺 ----------
    def restyle(self) -> None:
        self.configure(bg=theme.BG)
        self.preview.redraw()
