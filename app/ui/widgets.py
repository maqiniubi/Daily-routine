"""Apple 风格基础部件：圆角容器、圆角按钮、分段控件、开关、缓动动画。

tkinter 原生控件只有直角，所以这里用 Canvas 自绘圆角多边形：
- 半径随 DPI 缩放（theme.R）；
- 悬停/按下用 theme.mix 做颜色插值，配合 theme.ease_out 输出过渡；
- 所有动画都走 after 单链，不阻塞主循环。

这些部件只负责「长得对」，业务逻辑仍旧由各 tab 自己持有。
"""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable

from .. import theme


# ---------------- 几何 ----------------
def rounded_points(x0: float, y0: float, x1: float, y1: float, r: float,
                   samples: int = 6) -> list[float]:
    """圆角矩形的多边形顶点（Canvas 的 create_polygon 用）。"""
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    if r <= 0.5:
        return [x0, y0, x1, y0, x1, y1, x0, y1]
    pts: list[float] = []
    corners = (
        (x1 - r, y0 + r, -90.0, 0.0),      # 右上
        (x1 - r, y1 - r, 0.0, 90.0),       # 右下
        (x0 + r, y1 - r, 90.0, 180.0),     # 左下
        (x0 + r, y0 + r, 180.0, 270.0),    # 左上
    )
    for cx, cy, a0, a1 in corners:
        for i in range(samples + 1):
            a = math.radians(a0 + (a1 - a0) * i / samples)
            pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def animate(widget: tk.Misc, duration: int, step: Callable[[float], None],
            done: Callable[[], None] | None = None, frames: int = 12) -> str | None:
    """按 ease_out 时间曲线跑一段动画；duration 单位毫秒。"""
    try:
        if not widget.winfo_exists():
            return None
    except tk.TclError:
        return None
    interval = max(8, int(duration / frames))

    def tick(i: int) -> None:
        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return
        t = min(1.0, i / frames)
        try:
            step(theme.ease_out(t))
        except tk.TclError:
            return
        if t >= 1.0:
            if done is not None:
                try:
                    done()
                except tk.TclError:
                    pass
            return
        widget.after(interval, tick, i + 1)

    tick(0)
    return None


def star_points(cx: float, cy: float, outer: float, inner: float,
                spikes: int = 4, rot: float = -90.0) -> list[float]:
    """四角星（sparkle）顶点：外尖 + 内凹交替，用来当品牌标记。"""
    pts: list[float] = []
    for i in range(spikes * 2):
        r = outer if i % 2 == 0 else inner
        a = math.radians(rot + 180.0 * i / spikes)
        pts.extend((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


class Badge(tk.Canvas):
    """玻璃胶囊徽标：「✦ 永恒」。

    悬浮条、设置中心、贴纸都用它挂作者标记。半透明观感靠 theme.glass()
    预混实现（Canvas 没有 RGBA），点击可挂回调（默认打开「关于」）。
    """

    def __init__(self, parent, text: str = "永恒", *, command: Callable[[], None] | None = None,
                 bg: str | None = None, height: float = 24, font_role: str = "caption",
                 spark: str = "#ffd479", base: str | None = None,
                 fg: str | None = None, fg2: str | None = None, family: str = "ui"):
        self._bg = bg or parent.cget("bg")
        self._base = base or self._bg          # 玻璃叠色的基准（窗口底或卡片底）
        self._text = text
        self._spark = spark
        # 悬浮条与卡片是两套色板，文字色由调用方给；不给就用界面色
        self._fg = fg or theme.FG
        self._fg2 = fg2 or theme.FG2
        # family 决定换肤时去哪套色板里找对应角色（"ui" 设置中心 / "bar" 悬浮条）
        self._family = family
        self._bh = theme.S(height)
        self._font = theme.T(font_role)
        self._command = command
        self._hover = 0.0
        self._gen = 0
        f = tkfont.Font(family=self._font[0], size=self._font[1])
        self._label_w = f.measure(text)
        self._spark_w = theme.S(11)
        w = self._spark_w + theme.S(8) + self._label_w + theme.S(12)
        super().__init__(parent, width=w, height=self._bh, bg=self._bg,
                         highlightthickness=0, bd=0,
                         cursor="hand2" if command else "arrow")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._tween(1.0))
        self.bind("<Leave>", lambda e: self._tween(0.0))
        if command is not None:
            self.bind("<Button-1>", lambda e: command())
        self.after_idle(self._draw)

    def restyle(self) -> None:
        """换配色后重画（缓存的底色/基准色要先过一遍 remap）。"""
        fam = self._family
        self._bg = theme.remap(self._bg, "bg", fam)
        self._base = theme.remap(self._base, "bg", fam)
        self._fg = theme.remap(self._fg, "fg", fam)
        self._fg2 = theme.remap(self._fg2, "fg", fam)
        try:
            self.configure(bg=self._bg)
        except tk.TclError:
            return
        self._draw()

    def _tween(self, to: float) -> None:
        start = self._hover
        self._gen += 1
        gen = self._gen

        def step(t: float) -> None:
            if gen != self._gen:
                return
            self._hover = start + (to - start) * t
            self._draw()

        animate(self, 140, step)

    def _draw(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        hv = self._hover
        self.delete("all")
        # 胶囊底 + 描边：两层白色叠加，模拟玻璃的反射面
        self.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, h / 2),
                            fill=theme.glass(self._base, 0.07 + 0.06 * hv),
                            outline=theme.glass(self._base, 0.17 + 0.12 * hv), width=1)
        cx, cy = self._spark_w / 2 + theme.S(3), h / 2
        # 星芒外发光：很淡的一层，只为把标记从玻璃面上「托」起来
        gr = theme.S(6)
        self.create_oval(cx - gr, cy - gr, cx + gr, cy + gr,
                         fill=theme.mix(theme.glass(self._base, 0.07), self._spark,
                                        0.10 + 0.12 * hv), outline="")
        self.create_polygon(
            star_points(cx, cy, theme.S(5.2) + theme.S(0.5) * hv, theme.S(1.0)),
            fill=self._spark, outline="")
        self.create_text(cx + theme.S(9), cy, text=self._text, anchor="w",
                         fill=theme.mix(self._fg2, self._fg, 0.4 + 0.6 * hv),
                         font=self._font)


# ---------------- 圆角容器 ----------------
class RoundedBox(tk.Canvas):
    """圆角卡片：内容放进 `.body`（普通 Frame，可随意 pack/grid）。"""

    def __init__(self, parent, *, radius: float = 14, fill: str | None = None,
                 outline: str | None = None, pad: int = 0, bg: str | None = None,
                 hug: bool = True, **kw):
        self._bg = bg or parent.cget("bg") if bg is None else bg
        super().__init__(parent, bg=self._bg, highlightthickness=0, bd=0, **kw)
        self._radius = radius
        self._fill = fill or theme.CARD
        self._outline = outline if outline is not None else theme.LINE
        # 内容窗口必须内缩至少一个圆角半径，否则 Frame 的直角会把画出来的圆角盖掉，
        # 卡片就变成方盒子了（这个坑在 1.2.0 改版时踩过）。
        self._pad = max(pad, theme.R(radius))
        self._hugging = hug          # 标志位，勿与下面的 _hug() 方法重名
        self._shape: int | None = None
        self.body = tk.Frame(self, bg=self._fill)
        self._win = self.create_window(self._pad, self._pad, anchor="nw", window=self.body)
        self.bind("<Configure>", self._redraw)
        if hug:
            self.body.bind("<Configure>", self._hug)

    def _hug(self, _e=None) -> None:
        """让卡片高度贴合内容（宽度交给 pack/grid 决定）。"""
        try:
            need = self.body.winfo_reqheight() + self._pad * 2
        except tk.TclError:
            return
        if need > 0 and abs(self.winfo_reqheight() - need) > 1:
            try:
                self.configure(height=need)
            except tk.TclError:
                pass

    def fit(self) -> None:
        """把卡片尺寸收到内容大小（含圆角内缩）。"""
        try:
            self.update_idletasks()
            w = self.body.winfo_reqwidth() + self._pad * 2
            h = self.body.winfo_reqheight() + self._pad * 2
        except tk.TclError:
            return
        if w > 0 and h > 0:
            self.configure(width=w, height=h)

    def set_fill(self, color: str) -> None:
        self._fill = color
        self.body.configure(bg=color)
        self._draw_shape()

    def restyle(self) -> None:
        """换配色后就地换色：缓存的三处颜色过一遍 remap，再重画圆角。"""
        self._bg = theme.remap(self._bg, "bg")
        self._fill = theme.remap(self._fill, "bg")
        self._outline = theme.remap(self._outline, "bg")
        try:
            self.configure(bg=self._bg)
            self.body.configure(bg=self._fill)
        except tk.TclError:
            return
        self._draw_shape()

    def _draw_shape(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        if self._shape is not None:
            self.delete(self._shape)
        self._shape = self.create_polygon(
            rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(self._radius)),
            fill=self._fill, outline=self._outline, width=1, smooth=False)
        self.tag_lower(self._shape)

    def _redraw(self, event=None) -> None:
        w, h = (event.width, event.height) if event is not None else (
            self.winfo_width(), self.winfo_height())
        if w > 2 and h > 2:
            self.itemconfigure(self._win, width=w - self._pad * 2,
                               height=h - self._pad * 2)
        self._draw_shape()


def card(parent, *, fill: str | None = None, radius: float = 14, pad: int = 16,
         outline: str | None = None) -> tk.Frame:
    """便捷方法：返回卡片的 `.body`，外面那层圆角壳已就位。"""
    box = RoundedBox(parent, radius=radius, fill=fill, pad=pad, outline=outline)
    return box


# ---------------- 按钮 ----------------
#: 合法的按钮语气（颜色全部在 _colors() 里按当前主题现算，别在这里缓存色值）
_KINDS = ("primary", "secondary", "ghost", "danger", "glass")


class Button(tk.Canvas):
    """圆角按钮，带悬停/按下过渡。

    kind: primary（白底黑字）/ secondary（灰底）/ ghost（透明）/ danger
    fg / fg2: 可选，指定文字色与次要文字色（悬浮条上的按钮要用条的色板）。
    """

    def __init__(self, parent, text: str, command: Callable[[], None] | None = None,
                 *, kind: str = "secondary", width: int | None = None,
                 height: float = 30, radius: float = 8, font_role: str = "body-bold",
                 bg: str | None = None, icon: str = "", fg: str | None = None,
                 fg2: str | None = None, family: str = "ui"):
        self._parent_bg = bg or parent.cget("bg")
        self._font = theme.T(font_role)
        self._text = text
        self._icon = icon
        self._fg = fg or theme.FG
        self._fg2 = fg2 or theme.FG2
        self._family = family
        self._btn_h = theme.S(height)
        w = width or self._measure(text, icon) + theme.S(28)
        super().__init__(parent, width=w, height=self._btn_h, bg=self._parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._kind = kind if kind in _KINDS else "secondary"
        self._radius = radius
        self._command = command
        self._state = "normal"
        self._hover = 0.0
        self._pressed = False
        self._anim_job = None
        self._gen = 0                     # 动画代数：新动画一起步就让旧的失效
        self._shape: int | None = None
        self._label: int | None = None
        self.bind("<Configure>", lambda e: self._render())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.after_idle(self._render)

    # ---------- 尺寸 ----------
    def _measure(self, text: str, icon: str) -> int:
        f = tkfont.Font(family=self._font[0], size=self._font[1])
        return f.measure(f"{icon}{text}" if icon else text)

    def set_text(self, text: str) -> None:
        self._text = text
        self._render()

    def set_state(self, state: str) -> None:
        self._state = state
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self._render()

    def set_kind(self, kind: str) -> None:
        """换语气（secondary <-> primary），用于「预设方案」这类单选按钮。"""
        if kind in _KINDS and kind != self._kind:
            self._kind = kind
            self._render()

    def restyle(self) -> None:
        fam = self._family
        self._parent_bg = theme.remap(self._parent_bg, "bg", fam)
        self._fg = theme.remap(self._fg, "fg", fam)
        self._fg2 = theme.remap(self._fg2, "fg", fam)
        try:
            self.configure(bg=self._parent_bg)
        except tk.TclError:
            return
        self._render()

    # ---------- 渲染 ----------
    def _colors(self) -> tuple[str, str]:
        """返回 (底色, 文字色)，已叠加悬停/按下的插值。"""
        if self._state != "normal":
            return theme.SURFACE, theme.FG3

        if self._kind == "primary":
            bg = theme.mix(theme.FG, "#e2e2e8", self._hover * 0.9)
            fg = theme.BG
        elif self._kind == "glass":
            bg = theme.glass(self._parent_bg, 0.08 + 0.10 * self._hover)
            fg = theme.mix(self._fg2, self._fg, 0.45 + 0.55 * self._hover)
        elif self._kind == "ghost":
            bg = theme.mix(self._parent_bg, theme.CARD_HOVER, self._hover * 0.95)
            fg = theme.mix(self._fg2, self._fg, self._hover)
        else:
            bg = theme.mix(theme.CARD_HOVER, theme.FILL, self._hover)
            fg = theme.DANGER if self._kind == "danger" else self._fg

        if self._pressed:
            bg = theme.mix(bg, "#000000" if self._kind == "primary" else theme.FG,
                           0.10 if self._kind == "primary" else 0.06)
        return bg, fg

    def _render(self) -> None:
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        fill, fg = self._colors()
        self.delete("all")
        self.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(self._radius)),
                            fill=fill, outline="")
        if self._kind == "secondary":
            self.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(self._radius)),
                                fill="", outline=theme.LINE, width=1)
        elif self._kind == "glass":
            self.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, theme.R(self._radius)),
                                fill="", outline=theme.glass(self._parent_bg, 0.13), width=1)
        label = f"{self._icon} {self._text}" if self._icon else self._text
        self.create_text(w / 2, h / 2, text=label, fill=fg, font=self._font)

    # ---------- 交互 ----------
    def _tween(self, to: float) -> None:
        start = self._hover
        self._gen += 1                    # 让上一条动画链立刻失效
        gen = self._gen

        def step(t: float) -> None:
            if gen != self._gen:
                return
            self._hover = start + (to - start) * t
            self._render()

        animate(self, 120, step)

    def _on_enter(self, _e=None) -> None:
        if self._state == "normal":
            self._tween(1.0)

    def _on_leave(self, _e=None) -> None:
        self._pressed = False
        self._tween(0.0)

    def _on_press(self, _e=None) -> None:
        if self._state != "normal":
            return
        self._pressed = True
        self._render()

    def _on_release(self, _e=None) -> None:
        if self._state != "normal":
            return
        was = self._pressed
        self._pressed = False
        self._hover = 1.0 if self.winfo_containing(*self.winfo_pointerxy()) is self else 0.0
        self._render()
        if was and self._command is not None:
            try:
                self._command()
            except Exception:
                import logging
                logging.exception("按钮回调异常")


# ---------------- 分段控件 ----------------
class TabBar(tk.Frame):
    """苹果风格分段控件：胶囊高亮块会平滑滑动到选中项。"""

    def __init__(self, parent, items: list[str], on_change: Callable[[int], None],
                 *, bg: str | None = None, height: float = 34):
        self._bg = bg or parent.cget("bg")
        super().__init__(parent, bg=self._bg)
        self._items = items
        self._on_change = on_change
        self._index = 0
        self._pill_x = 0.0
        self._pill_w = 0.0
        self._gen = 0                     # 动画代数：新滑动一起步就让旧的 tick 失效
        self._bar_h = theme.S(height)
        self._font = theme.T("body-bold")
        self._font_idle = theme.T("body")

        self.canvas = tk.Canvas(self, bg=self._bg, highlightthickness=0, bd=0,
                                height=self._bar_h + theme.S(8), cursor="hand2")
        self.canvas.pack(fill="x")
        self._widths: list[int] = []
        self._measure()
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda e: self._draw(hover=-1))

    def _measure(self) -> None:
        f = tkfont.Font(family=self._font[0], size=self._font[1])
        pad = theme.S(18)
        self._widths = [f.measure(t) + pad * 2 for t in self._items]
        total = sum(self._widths) + theme.S(4) * (len(self._items) + 1)
        self.canvas.configure(width=total, height=self._bar_h + theme.S(8))

    def _layout(self) -> tuple[list[float], float]:
        """返回每一项的左边界与胶囊宽度。"""
        gap = theme.S(4)
        x = gap
        xs: list[float] = []
        for w in self._widths:
            xs.append(x)
            x += w + gap
        return xs, gap

    def _on_resize(self, _e=None) -> None:
        self._draw()

    def restyle(self) -> None:
        self._bg = theme.remap(self._bg, "bg")
        try:
            self.configure(bg=self._bg)
            self.canvas.configure(bg=self._bg)
        except tk.TclError:
            return
        self._draw()

    def _draw(self, hover: int = -2) -> None:
        cv = self.canvas
        cv.delete("all")
        xs, gap = self._layout()
        h = self._bar_h
        top = theme.S(4)
        # 轨道
        cv.create_polygon(rounded_points(0, top, sum(self._widths) + gap * (len(xs) + 1),
                                          top + h, theme.R(h / 2)),
                          fill=theme.SURFACE, outline=theme.LINE, width=1)
        # 胶囊
        if self._pill_w > 0:
            cv.create_polygon(rounded_points(self._pill_x, top + theme.S(3),
                                             self._pill_x + self._pill_w, top + h - theme.S(3),
                                             theme.R((h - theme.S(6)) / 2)),
                              fill=theme.PILL, outline=theme.mix(theme.PILL, theme.FG, 0.14),
                              width=1)
        for i, text in enumerate(self._items):
            cx = xs[i] + self._widths[i] / 2
            color = theme.FG if i == self._index else (
                theme.FG if i == hover else theme.FG2)
            cv.create_text(cx, top + h / 2, text=text, fill=color,
                           font=self._font if i == self._index else self._font_idle)

    def _id_at(self, x: float) -> int:
        xs, _ = self._layout()
        for i, left in enumerate(xs):
            if left <= x <= left + self._widths[i]:
                return i
        return -1

    def _on_motion(self, event) -> None:
        self._draw(hover=self._id_at(event.x))

    def _on_click(self, event) -> None:
        i = self._id_at(event.x)
        if i >= 0 and i != self._index:
            self.select(i)

    def select(self, index: int, animated: bool = True) -> None:
        """切换选中项；animated=False 时直接跳到位（首帧初始化用）。

        注意：参数不能叫 animate —— 会遮蔽模块级的 animate() 动画函数。
        """
        index = max(0, min(len(self._items) - 1, index))
        xs, _ = self._layout()
        target_x = xs[index] + theme.S(3)
        target_w = self._widths[index] - theme.S(6)
        old_index = self._index
        self._index = index
        self._gen += 1                    # 上一次滑动还没跑完时，先让它的 tick 失效
        gen = self._gen
        if not animated or self._pill_w == 0:
            self._pill_x, self._pill_w = target_x, target_w
            self._draw()
        else:
            start_x, start_w = self._pill_x, self._pill_w

            def step(t: float) -> None:
                if gen != self._gen:
                    return
                self._pill_x = start_x + (target_x - start_x) * t
                self._pill_w = start_w + (target_w - start_w) * t
                self._draw()

            animate(self.canvas, 200, step)
        if index != old_index:
            self._on_change(index)

    def current(self) -> int:
        return self._index


# ---------------- 开关 ----------------
class Switch(tk.Canvas):
    """iOS 风格开关，替代 tk.Checkbutton（后者在深色下太丑）。"""

    def __init__(self, parent, value: bool = False,
                 command: Callable[[bool], None] | None = None, *, bg: str | None = None):
        self._bg = bg or parent.cget("bg")
        # 注意：不能用 self._w / self._h —— tkinter 的 Misc._w 是控件路径名，
        # 会被 super().__init__() 覆盖成字符串，之后参与算术就会抛 TypeError。
        self._cw, self._ch = theme.S(42), theme.S(24)
        super().__init__(parent, width=self._cw, height=self._ch, bg=self._bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._value = bool(value)
        self._pos = 1.0 if value else 0.0
        self._gen = 0                     # 动画代数：连点开关时避免两条动画互相覆盖
        self._command = command
        self.bind("<Button-1>", self._toggle)
        self.after_idle(self._draw)

    def set(self, value: bool, animated: bool = True) -> None:
        value = bool(value)
        if value == self._value:
            self._draw()
            return
        self._value = value
        target = 1.0 if value else 0.0
        self._gen += 1
        gen = self._gen
        if not animated:
            self._pos = target
            self._draw()
            return
        start = self._pos

        def step(t: float) -> None:
            if gen != self._gen:
                return
            self._pos = start + (target - start) * t
            self._draw()

        animate(self, 180, step)

    def get(self) -> bool:
        return self._value

    def restyle(self) -> None:
        self._bg = theme.remap(self._bg, "bg")
        try:
            self.configure(bg=self._bg)
        except tk.TclError:
            return
        self._draw()

    def _toggle(self, _e=None) -> None:
        self.set(not self._value)
        if self._command is not None:
            try:
                self._command(self._value)
            except Exception:
                import logging
                logging.exception("开关回调异常")

    def _draw(self) -> None:
        w, h = self._cw, self._ch
        r = h / 2
        self.delete("all")
        track = theme.mix(theme.FILL, theme.ACCENT, self._pos)
        self.create_polygon(rounded_points(0.5, 0.5, w - 0.5, h - 0.5, r),
                            fill=track, outline="")
        knob_r = r - theme.S(2.5)
        cx = r + theme.S(1) + (w - 2 * r - theme.S(2)) * self._pos
        cy = h / 2
        self.create_oval(cx - knob_r, cy - knob_r, cx + knob_r, cy + knob_r,
                         fill="#ffffff", outline="")


class DayPicker(tk.Frame):
    """七个可点的星期方块：点亮 = 那天执行定时关机。

    不用 ttk.Checkbutton：Windows 下深色主题会给它套一圈浅色边框，
    七个挤在一行像排错误提示。这里用 Label + 背景色切换，和 Switch 同一套语汇，
    也让「哪几天生效」一眼能扫完。
    """

    LABELS = ("一", "二", "三", "四", "五", "六", "日")

    def __init__(self, parent, on_change=None, days=(), bg: str | None = None):
        bg = bg or theme.CARD
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._on_change: Callable | None = on_change
        self._days: set[int] = {int(d) for d in (days or ()) if 0 <= int(d) <= 6}
        self._cells: list[tk.Label] = []
        for i, name in enumerate(self.LABELS):
            cell = tk.Label(self, text=name, width=2, bd=0, padx=0, pady=theme.S(2),
                            font=theme.T("caption"), cursor="hand2",
                            bg=theme.CARD_HOVER, fg=theme.FG2)
            cell.pack(side="left", padx=(0 if i == 0 else theme.S(3), 0))
            cell.bind("<Button-1>", lambda _e, idx=i: self.toggle(idx))
            self._cells.append(cell)
        self._paint()

    # ---------- 对外 ----------
    def get(self) -> list[int]:
        return sorted(self._days)

    def set(self, days) -> None:
        self._days = {int(d) for d in (days or ()) if 0 <= int(d) <= 6}
        self._paint()

    def toggle(self, index: int) -> None:
        if index in self._days:
            self._days.discard(index)
        else:
            self._days.add(index)
        self._paint()
        if self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                import logging
                logging.exception("星期选择回调异常")

    # ---------- 内部 ----------
    def restyle(self) -> None:
        self._bg = theme.remap(self._bg, "bg")
        try:
            self.configure(bg=self._bg)
        except tk.TclError:
            return
        self._paint()

    def _paint(self) -> None:
        for i, cell in enumerate(self._cells):
            on = i in self._days
            cell.configure(bg=theme.ACCENT if on else theme.CARD_HOVER,
                           fg=theme.ON_ACCENT if on else theme.FG2)
