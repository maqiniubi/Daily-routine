"""桌面顶部悬浮条：半透明玻璃质地、圆角、高度自适应、始终置顶。

玻璃的实现（tkinter 能做到的上限，别指望真模糊）：

1. **整窗 alpha**（0.86）——壁纸从条面上透出来，这是「半透明」的来源。
2. **SetWindowRgn 圆角裁剪**——真圆角，四角与壁纸直接相接，不是「画个圆角盖在方窗口上」。
   `-alpha` 与 `-transparentcolor` 在 Win32 层互斥，只有 window region 能和 layered 共存。
3. **DWM acrylic 不参与**：实测（tools/_probe_glass.py）对 layered 窗口不产生模糊，
   调用了也只是多染一层色，反而不可控，所以不用。
4. 剩下的「玻璃感」全交给光学暗示：顶部 1px 高光（中间亮两端淡）、底部内阴影、
   内嵌控件一律用 `theme.glass()` 预混的半透明白叠层。

信息结构保持三段式：日期/作息 → 当前状态 → 时钟/操作，右侧挂「✦ 永恒」标识。
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime

from .. import theme, win32util
from ..models import DAY_KEYS, DAY_NAMES
from ..scheduler import day_state, hhmm, hhmmss
from .timeaxis import TimeAxis
from .widgets import Badge, Button, rounded_points

#: 玻璃条相对屏幕边缘的留白与顶部偏移（dp）
OFFSET_Y = 8

#: 中间「课程名称」显示区的默认高度（dp）。
#: 两行文字的自然高度约 41dp，56 相当于上下各留 7dp 呼吸位。
COURSE_AREA_H = 56
COURSE_AREA_MIN = 28
COURSE_AREA_MAX = 96


class TopBar:
    def __init__(self, root: tk.Tk, ctl):
        self.root = root
        self.ctl = ctl
        self.win = root
        self.win.overrideredirect(True)
        self.win.configure(bg=theme.GLASS)
        self._hwnd = 0
        self._screen_w = self.win.winfo_screenwidth()
        self._inset = theme.S(theme.GLASS_INSET)
        self._off_y = theme.S(OFFSET_Y)
        self._bar_h = theme.S(64)
        self._win_w = self._screen_w - self._inset * 2
        self._alpha = self._read_alpha()
        self._through = self._read_through()
        self._font_scale = float(self.ctl.data.settings.get("font_scale", 1.0))
        self._guard_ms = int(self.ctl.data.settings.get("topmost_guard_ms", 1000))
        self._last_state = None
        self._now = datetime.now()
        self._text_w_cache: dict[tuple[str, float], float] = {}

        self._shell = tk.Frame(self.win, bg=theme.GLASS)
        self._shell.pack(fill="both", expand=True)
        self._build()
        self._apply_geometry()
        win32util.set_window_alpha(self.win, self._alpha)

        self.win.after(40, self._post_init)
        self._guard_job = None
        self.win.after(100, self._guard)
        self.win.after(200, self._tick)

    def _read_alpha(self) -> float:
        try:
            return max(0.55, min(1.0, float(self.ctl.data.settings.get(
                "bar_alpha", theme.GLASS_ALPHA))))
        except Exception:
            return theme.GLASS_ALPHA

    def _course_area_h(self) -> int:
        """课程名称显示区的高度（dp 配置 -> 物理像素）。"""
        try:
            dp = int(self.ctl.data.settings.get("course_area_h", COURSE_AREA_H))
        except Exception:
            dp = COURSE_AREA_H
        return theme.S(max(COURSE_AREA_MIN, min(COURSE_AREA_MAX, dp)))

    def _read_through(self) -> bool:
        return bool(self.ctl.data.settings.get("click_through", True))

    def set_click_through(self, enable: bool) -> None:
        """整条悬浮条鼠标穿透：开启后条面不再接收任何鼠标消息，点哪都是点桌面。"""
        self._through = bool(enable)
        if self._hwnd:
            win32util.set_click_through(self._hwnd, self._through)

    # ---------------- 构建 ----------------
    def F(self, px: float, bold: bool = False):
        return theme.F(px * self._font_scale, bold)

    def _build(self) -> None:
        for child in self._shell.winfo_children():
            child.destroy()

        # 换肤清单：restyle() 靠它就地换色，不必整条重建
        self._glass_frames: list[tk.Frame] = []
        self._bar_labels: list[tuple[tk.Label, str]] = []
        self._bar_badge: Badge | None = None
        self._bar_button: Button | None = None

        # 顶部高光：1px 的「边缘反光」，是玻璃最关键的暗示
        self.cv_gloss = tk.Canvas(self._shell, bg=theme.GLASS, highlightthickness=0, bd=0,
                                  height=max(1, theme.S(1)))
        self.cv_gloss.pack(fill="x", side="top")
        self.cv_gloss.bind("<Configure>", lambda e: self._draw_gloss())

        self.header = tk.Frame(self._shell, bg=theme.GLASS)
        self.header.pack(fill="x", padx=theme.P(5), pady=(theme.S(7), theme.S(4)))
        self.header.columnconfigure(1, weight=1)
        self._glass_frames.append(self.header)

        # 左：日期 / 星期 / 作息名 / 倒计时
        left = tk.Frame(self.header, bg=theme.GLASS)
        left.grid(row=0, column=0, sticky="w")
        self._glass_frames.append(left)
        self.lbl_date = tk.Label(left, text="", bg=theme.GLASS, fg=theme.BAR_FG,
                                 font=self.F(14, True), anchor="w")
        self.lbl_date.pack(side="left")
        self._bar_labels.append((self.lbl_date, "BAR_FG"))
        self.lbl_plan = tk.Label(left, text="", bg=theme.GLASS, fg=theme.BAR_FG2, font=self.F(11),
                                 anchor="w")
        self.lbl_plan.pack(side="left", padx=(theme.S(10), 0))
        self._bar_labels.append((self.lbl_plan, "BAR_FG2"))
        self.lbl_cd = tk.Label(left, text="", bg=theme.GLASS, fg=theme.BAR_FG, font=self.F(11, True),
                               anchor="w")
        self.lbl_cd.pack(side="left", padx=(theme.S(10), 0))
        self._bar_labels.append((self.lbl_cd, "BAR_FG"))

        # 中：当前状态（课程名称显示区）。高度由设置决定，内容在其中垂直居中。
        mid = tk.Frame(self.header, bg=theme.GLASS)
        mid.grid(row=0, column=1, sticky="nsew")
        self._glass_frames.append(mid)
        inner = tk.Frame(mid, bg=theme.GLASS)
        inner.pack(expand=True)      # 让两行文字在加高后的区域里上下居中
        self._glass_frames.append(inner)
        self.lbl_state = tk.Label(inner, text="", bg=theme.GLASS, fg=theme.BAR_FG,
                                  font=self.F(15, True))
        self.lbl_state.pack()
        self._bar_labels.append((self.lbl_state, "BAR_FG"))
        self.lbl_sub = tk.Label(inner, text="", bg=theme.GLASS, fg=theme.BAR_FG3, font=self.F(10))
        self.lbl_sub.pack()
        self._bar_labels.append((self.lbl_sub, "BAR_FG3"))
        # 高度固定：关闭尺寸传播后 height 才生效；但下限取「内容实际需要」，
        # 这样把文字缩放到 1.4 倍时也不会被裁掉半行。
        inner.update_idletasks()
        mid.configure(height=max(self._course_area_h(), inner.winfo_reqheight() + theme.S(2)))
        mid.pack_propagate(False)

        # 右：永恒标识 + 时钟 + 按钮
        right = tk.Frame(self.header, bg=theme.GLASS)
        right.grid(row=0, column=2, sticky="e")
        self._glass_frames.append(right)
        self._bar_badge = Badge(right, "永恒", command=self.ctl.show_about, bg=theme.GLASS,
                                height=24, fg=theme.BAR_FG, fg2=theme.BAR_FG2, family="bar")
        self._bar_badge.pack(side="left", padx=(0, theme.P(3)))
        self.lbl_clock = tk.Label(right, text="00:00:00", bg=theme.GLASS, fg=theme.BAR_FG,
                                  font=self.F(19, True))
        self.lbl_clock.pack(side="left", padx=(0, theme.P(3)))
        self._bar_labels.append((self.lbl_clock, "BAR_FG"))
        self._bar_button = Button(right, "设置", self.ctl.open_settings, kind="glass", height=26,
                                  width=theme.S(56), radius=7, bg=theme.GLASS,
                                  fg=theme.BAR_FG, fg2=theme.BAR_FG2, family="bar")
        self._bar_button.pack(side="left")

        # 24 小时进度条
        self.cv_day = None
        if self.ctl.data.settings.get("show_24h_bar", True):
            self.cv_day = tk.Canvas(self._shell, bg=theme.GLASS, highlightthickness=0,
                                    height=theme.S(40))
            self.cv_day.pack(fill="x", padx=theme.P(5), pady=(0, theme.S(2)))
            self.cv_day.bind("<Configure>", lambda e: self._draw_day())

        # 今日时段条
        self.cv_slots = None
        if self.ctl.data.settings.get("show_slot_bar", True):
            self.cv_slots = tk.Canvas(self._shell, bg=theme.GLASS, highlightthickness=0,
                                      height=theme.S(26))
            self.cv_slots.pack(fill="x", padx=theme.P(5), pady=(0, theme.S(5)))
            self.cv_slots.bind("<Configure>", lambda e: self._draw_slots())

        # 底部内阴影：比描边更「玻璃」，像玻璃板下沿的暗边
        self.cv_edge = tk.Canvas(self._shell, bg=theme.GLASS, highlightthickness=0, bd=0,
                                 height=max(1, theme.S(1)))
        self.cv_edge.pack(fill="x", side="bottom")
        self.cv_edge.bind("<Configure>", lambda e: self._draw_edge())

        for w in (self._shell, self.header, self.lbl_state, self.lbl_date):
            w.bind("<Double-Button-1>", lambda e: self.ctl.open_settings())
        self.win.bind("<Button-3>", self._popup_menu)

    # ---------------- 玻璃表面 ----------------
    def _draw_gloss(self) -> None:
        """顶沿高光：中间最亮、两端收淡，模拟光源从上方照在玻璃边上。"""
        cv = getattr(self, "cv_gloss", None)
        if cv is None:
            return
        cv.delete("all")
        w = cv.winfo_width()
        if w <= 2:
            return
        seg = 48
        for i in range(seg):
            t = i / (seg - 1)
            a = 0.045 + 0.30 * (1.0 - abs(t - 0.5) * 2) ** 0.7
            x0 = w * i / seg
            cv.create_rectangle(x0, 0, x0 + w / seg + 1, max(1, theme.S(1)),
                                fill=theme.mix(theme.GLASS, "#ffffff", a), outline="")

    def _draw_edge(self) -> None:
        cv = getattr(self, "cv_edge", None)
        if cv is None:
            return
        cv.delete("all")
        w = cv.winfo_width()
        if w > 2:
            cv.create_rectangle(0, 0, w, max(1, theme.S(1)),
                                fill=theme.BAR_EDGE, outline="")

    # ---------------- 初始化 / 置顶守护 ----------------
    def _post_init(self) -> None:
        self._hwnd = win32util.hwnd_of(self.win)
        win32util.make_tool_window(self._hwnd)
        self.win.attributes("-topmost", True)
        self._apply_geometry()          # 有 hwnd 了，补一次圆角裁剪
        win32util.push_topmost(self._hwnd)
        win32util.set_click_through(self._hwnd, self._through)

    def _guard(self) -> None:
        """低频重申置顶，防止被其它置顶窗口 / 全屏窗口盖住。"""
        try:
            if self.ctl.data.settings.get("topmost_guard_ms") != self._guard_ms:
                self._guard_ms = int(self.ctl.data.settings.get("topmost_guard_ms", 1000))
            self.win.attributes("-topmost", True)
            win32util.push_topmost(self._hwnd)
        except Exception:
            pass
        self._guard_job = self.win.after(max(300, self._guard_ms), self._guard)

    # ---------------- 尺寸 ----------------
    def _apply_geometry(self) -> None:
        self._shell.update_idletasks()
        h = self._shell.winfo_reqheight()
        self._bar_h = max(theme.S(36), h)
        self._screen_w = self.win.winfo_screenwidth()
        self._win_w = max(theme.S(320), self._screen_w - self._inset * 2)
        self.win.geometry(f"{self._win_w}x{self._bar_h}+{self._inset}+{self._off_y}")
        if self._hwnd:
            win32util.set_round_region(self._hwnd, self._win_w, self._bar_h,
                                       theme.R(theme.GLASS_RADIUS))

    def height(self) -> int:
        """条体占用的总高度（含顶部偏移），供设置中心 / 提醒气泡避让。"""
        return self._bar_h + self._off_y

    def set_alpha(self, value: float) -> None:
        """玻璃强度：1.0 = 不透明，越低越透。"""
        self._alpha = max(0.55, min(1.0, float(value)))
        win32util.set_window_alpha(self.win, self._alpha)

    def _popup_menu(self, event) -> None:
        menu = tk.Menu(self.win, tearoff=0, bg=theme.CARD_HOVER, fg=theme.FG,
                       activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT,
                       bd=0, font=theme.F(11), activeborderwidth=0)
        menu.add_command(label="设置中心", command=self.ctl.open_settings)
        menu.add_command(label="重新校准并置顶", command=self.recalibrate)
        menu.add_separator()
        menu.add_command(label="赞赏支持", command=self.ctl.show_sponsor)
        menu.add_command(label="关于（退出请在托盘图标右键）", command=self.ctl.show_about)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def recalibrate(self) -> None:
        """对外：重新测量并重申置顶。"""
        win32util.push_topmost(self._hwnd)
        self._apply_geometry()
        self._tick()

    def refresh_countdown(self) -> None:
        """悬浮条上的倒计时（最多两条，按剩余天数排序）。"""
        lbl = getattr(self, "lbl_cd", None)
        if lbl is None:
            return
        try:
            items = self.ctl.data.bar_countdowns()
        except Exception:
            items = []
        if not items:
            lbl.configure(text="")
            return
        lbl.configure(text="　·　" + "　·　".join(c.short() for c in items))

    def refresh(self) -> None:
        """数据或设置变化后重建界面并重新自适应高度。"""
        self._font_scale = float(self.ctl.data.settings.get("font_scale", 1.0))
        self._alpha = self._read_alpha()
        self._through = self._read_through()
        # 配色可能换过：窗口与外壳的底色也要一起刷，否则圆角/内边距处会露出旧色
        try:
            self.win.configure(bg=theme.GLASS)
            self._shell.configure(bg=theme.GLASS)
        except tk.TclError:
            return
        self._build()
        self._apply_geometry()
        win32util.set_window_alpha(self.win, self._alpha)
        if self._hwnd:
            win32util.push_topmost(self._hwnd)
            win32util.set_click_through(self._hwnd, self._through)
        self._tick()

    def restyle(self) -> None:
        """换配色后就地换色：结构没变，不必整条销毁重建。

        v1.6.0 之前换配色走的是 refresh() → _build()，把每个控件 destroy 掉重建，
        实测单次 142 ms（占一次切换耗时的四成），拖动透明度滑块时肉眼可见地卡。
        这里改成「按令牌回填 + 重画画布」，代价降到几毫秒。

        只有结构变了（字号缩放、进度条开关、课程区高度）才需要 refresh()。
        """
        try:
            self.win.configure(bg=theme.GLASS)
            self._shell.configure(bg=theme.GLASS)
        except tk.TclError:
            return
        self._alpha = self._read_alpha()      # 通透度可能一起被改了
        for frame in self._glass_frames:
            try:
                frame.configure(bg=theme.GLASS)
            except tk.TclError:
                pass
        for label, token in self._bar_labels:
            try:
                label.configure(bg=theme.GLASS, fg=theme.get(token))
            except tk.TclError:
                pass
        # 自绘部件：用悬浮条色板（family="bar"）回填，别混进界面色板
        badge = self._bar_badge
        if badge is not None:
            badge._bg = theme.GLASS
            badge._base = theme.GLASS
            badge._fg = theme.BAR_FG
            badge._fg2 = theme.BAR_FG2
            badge.restyle()
        button = self._bar_button
        if button is not None:
            button._parent_bg = theme.GLASS
            button._fg = theme.BAR_FG
            button._fg2 = theme.BAR_FG2
            button.restyle()
        # 画布：换底色并重画（进度条 / 时段条 / 高光 / 内阴影都是自绘的）
        for canvas in (self.cv_gloss, self.cv_day, self.cv_slots, self.cv_edge):
            if canvas is None:
                continue
            try:
                canvas.configure(bg=theme.GLASS)
            except tk.TclError:
                pass
        self._draw_gloss()
        self._draw_day()
        self._draw_slots()
        self._draw_edge()
        # 不重算几何：配色不影响尺寸与圆角区域，重算一次要十几毫秒
        win32util.set_window_alpha(self.win, self._alpha)

    # ---------------- 主循环 ----------------
    def _tick(self) -> None:
        now = datetime.now()
        try:
            self.ctl.on_tick(now)
            state = day_state(self.ctl.data, now)
            self._last_state = state
            self._render(now, state)
        except Exception:
            pass
        self.win.after(1000, self._tick)

    def _render(self, now: datetime, state: dict) -> None:
        self._now = now
        day_name = DAY_NAMES[DAY_KEYS.index(state["key"])]
        sched = self.ctl.data.schedule_for_day(state["key"])
        self.lbl_date.configure(text=f"{now:%m月%d日}  {day_name}")
        self.lbl_plan.configure(text=f"· {sched.name}")
        self.lbl_clock.configure(text=f"{now:%H:%M:%S}")

        current = state["current"]
        nxt = state["next"]
        if current:
            if current.is_class:
                head = f"正在上课 · {current.course or current.period.name}"
            else:
                head = f"{current.period.name}中"
            sub = f"剩余 {hhmmss(state['left'])}"
            if nxt:
                sub += f"　·　下一节 {nxt.label()} {hhmm(nxt.start_s)}"
        elif nxt:
            head = f"距 {nxt.label()} 还有 {hhmmss(state['rest'])}"
            sub = f"开始时间 {hhmm(nxt.start_s)}"
        elif state["finished"]:
            head = "今日作息已结束"
            sub = "好好休息，晚安"
        else:
            head = "今日暂无安排"
            sub = "在「设置中心」中添加作息时段"

        self.lbl_state.configure(text=head)
        self.lbl_sub.configure(text=sub)
        self.refresh_countdown()
        self._draw_day()
        self._draw_slots()

    # ---------------- 绘图：公共 ----------------
    def _canvas_w(self, cv) -> int:
        """画布可用宽度。首帧还没完成布局时按「条宽 - 左右内边距」估算，
        绝不能用整条宽度——那会把最右边的时段块画到画布外面去（看起来像被切掉）。"""
        w = cv.winfo_width()
        if w > 2:
            return w
        return max(theme.S(120), self._win_w - theme.P(5) * 2)

    def _time_axis(self) -> TimeAxis:
        """今天的时间轴（压缩空白后）。上面进度条与下面时段条共用它，
        这样 09:50 的课块一定压在同一时刻的刻度下方。

        不做缓存：一次构建只有几十次浮点运算，而按 `id(state["slots"])` 缓存
        会踩对象 id 复用的坑（旧列表被回收后新列表可能拿到同一个 id）。
        """
        cv = self.cv_slots or self.cv_day
        state = self._last_state or {}
        w = self._canvas_w(cv) if cv is not None else self._win_w
        return TimeAxis(state.get("slots") or [], theme.S(1), w - theme.S(1))

    def _compressed_spans(self, axis: TimeAxis):
        for t0, t1 in axis.compressed:
            a, b = axis.to_x(t0), axis.to_x(t1)
            if b - a >= theme.S(2):
                yield a, b

    def _shade_compressed(self, cv, axis: TimeAxis, y0: float, y1: float) -> None:
        """压缩区铺 45° 淡斜纹，表示「这一段被折叠过」。

        不能用实心暗块：高度和课块一样、宽度也差不多的暗块，看上去就像真的有一节课。
        斜纹是「非数据」的通用记号，又不会抢课块的注意力。

        斜纹全部拼成**一条** create_line（偶数个坐标 = 若干独立线段）：
        1920 屏上压缩区能有几百条斜线，逐条 create_line 要几百次 Tcl 往返，
        换一次配色光这一处就要十几毫秒。
        """
        color = theme.mix(theme.BAR_BG, theme.BAR_FG3, 0.55)
        step = max(4, theme.S(5))
        h = y1 - y0
        for a, b in self._compressed_spans(axis):
            pts: list[float] = []
            c = a - h
            while c <= b:
                # 直线族 x - y = c，取它与矩形 [a,b]×[y0,y1] 的实际交集
                xa, xb = max(a, c + y0), min(b, c + y1)
                if xb - xa > 0.6:
                    pts.extend((xa, xa - c, xb, xb - c))
                c += step
            if pts:
                cv.create_line(*pts, fill=color, width=1)

    def _hatch_compressed(self, cv, axis: TimeAxis, y0: float, y1: float) -> None:
        """压缩区中央画一对短斜线 —— 工程图里「此处省略」的记号。

        只画一个符号、不铺满整段：铺满会变成噪点，反而看不清课块。
        区段太窄（< 10dp）就只留暗底，符号挤在里面像脏点。
        """
        cy = (y0 + y1) / 2
        color = theme.mix(theme.BAR_BG, theme.BAR_FG3, 0.95)
        for a, b in self._compressed_spans(axis):
            if b - a < theme.S(10):
                continue
            cx = (a + b) / 2
            for k in (-1, 1):
                x = cx + k * theme.S(2.2)
                cv.create_line(x - theme.S(1.4), cy + theme.S(3),
                               x + theme.S(1.4), cy - theme.S(3),
                               fill=color, width=max(1, theme.S(1)))

    def _slot_font(self):
        """量文字宽度用的 Font，随「文字缩放」一起变，每种缩放只建一次。"""
        if getattr(self, "_slot_font_key", None) != self._font_scale:
            fam, size = self.F(9)[0], self.F(9)[1]
            self._slot_font_obj = tkfont.Font(root=self.win, family=fam, size=size)
            self._slot_font_key = self._font_scale
            self._text_w_cache.clear()
        return self._slot_font_obj

    def _measure_text(self, text: str) -> float:
        """量文字宽度（带缓存）。

        ``tkfont.measure`` 一次要近 1 ms——中文还要走一遍字形整形；
        而时段条每次重绘都要量十几个名字（算省略号还要再量几次）。
        名称在两次重绘之间基本不变，缓存住就够。
        """
        cache = getattr(self, "_text_w_cache", None)
        if cache is None:
            cache = self._text_w_cache = {}
        key = (text, self._font_scale)
        width = cache.get(key)
        if width is None:
            width = self._slot_font().measure(text)
            cache[key] = width
        return width

    def _fit_slot_text(self, text: str, max_w: float) -> str:
        """按实际字宽决定时段名称怎么画：整名 → 逐字省略 → 留白。

        以前用的是固定像素阈值（块宽 > 46dp 才写字），30 分钟的小节永远轮不到写字，
        就出现「最右边一个白块、里面空的」这种观感。
        """
        if not text or max_w <= theme.S(10):
            return ""
        pad = theme.S(6)
        if self._measure_text(text) + pad <= max_w:
            return text
        for cut in range(len(text) - 1, 0, -1):
            cand = text[:cut] + "…"
            if self._measure_text(cand) + pad <= max_w:
                return cand
        return ""

    # ---------------- 绘图：24 小时进度 ----------------
    def _draw_day(self) -> None:
        cv = self.cv_day
        if cv is None:
            return
        cv.delete("all")
        # 坐标系一律取自 axis：两条画布若各算各的宽度，压缩后会有 1px 级错位
        axis = self._time_axis()
        x0, x1 = axis.x0, axis.x1
        bar_y = theme.S(17)          # 轨道中线：上方留给百分比胶囊，下方留给刻度
        half = theme.S(1.5)

        # 凹槽：压暗的玻璃槽 + 内侧暗边，比纯色轨道更像「嵌进玻璃里」
        cv.create_polygon(rounded_points(x0, bar_y - half, x1, bar_y + half, half),
                          fill=theme.BAR_TRACK, outline="")

        # 刻度跟着压缩走：挤不下的整点自动跳过，不再固定 0/6/12/18/24 五点
        for hour, x in axis.hour_ticks(theme.S(54)):
            cv.create_line(x, bar_y - half - theme.S(2), x, bar_y + half + theme.S(3),
                           fill=theme.BAR_TICK if hour % 6 == 0 else theme.BAR_TICK_WEAK)
            anchor = ("w" if x - x0 < theme.S(16)
                      else ("e" if x1 - x < theme.S(16) else "center"))
            cv.create_text(x, bar_y + theme.S(14), text=f"{hour:02d}:00", anchor=anchor,
                           fill=theme.BAR_FG3, font=self.F(9))

        now = getattr(self, "_now", None) or datetime.now()
        ratio = (now.hour * 3600 + now.minute * 60 + now.second) / 86400.0
        nx = axis.to_x(now.hour * 3600 + now.minute * 60 + now.second)
        cv.create_polygon(rounded_points(x0, bar_y - half, max(x0 + 2, nx), bar_y + half, half),
                          fill=theme.BAR_FG, outline="")
        cv.create_oval(nx - theme.S(3), bar_y - theme.S(3), nx + theme.S(3), bar_y + theme.S(3),
                       fill=theme.BAR_FG, outline=theme.GLASS, width=theme.S(1.5))
        # 记号必须压在白色进度段之上：凌晨那段永远是「已过」，先画就被盖没了
        self._hatch_compressed(cv, axis, bar_y - half, bar_y + half)

        # 百分比标签不能直接压在白色进度段上（同明度会糊成一片）：
        # 贴在轨道上方，并铺一块玻璃胶囊保证任何位置都能读清。
        label = f"{ratio * 100:.1f}%"
        left_side = nx < (x0 + x1) / 2
        tip = nx + theme.S(9) if left_side else nx - theme.S(9)
        chip_w = theme.S(38)
        cx0 = tip - theme.S(2) if left_side else tip + theme.S(2) - chip_w
        cx0 = max(x0, min(x1 - chip_w, cx0))
        cv.create_polygon(rounded_points(cx0, theme.S(1), cx0 + chip_w, theme.S(13), theme.S(6)),
                          fill=theme.mix(theme.GLASS, theme.BAR_LINE, 0.22),
                          outline=theme.mix(theme.GLASS, theme.BAR_LINE, 0.40), width=1)
        cv.create_text(cx0 + chip_w / 2, theme.S(7), text=label,
                       fill=theme.BAR_FG, font=self.F(9, True))

    # ---------------- 绘图：今日时段条 ----------------
    def _draw_slots(self) -> None:
        cv = self.cv_slots
        if cv is None:
            return
        cv.delete("all")
        state = self._last_state
        if not state or not state["slots"]:
            cv.create_text(theme.S(2), cv.winfo_height() // 2, text="今日暂无作息时段",
                           anchor="w", fill=theme.BAR_FG3, font=self.F(10))
            return

        y0 = theme.S(2)
        hh = theme.S(13)
        axis = self._time_axis()
        to_x = axis.to_x
        # 压缩区（凌晨 / 大空档）先垫暗底，让「这段被折叠了」有底色可认
        self._shade_compressed(cv, axis, y0, y0 + hh)

        # 整点网格：与上面刻度共用同一套压缩坐标，两条才是同一条时间轴
        for hour, gx in axis.hour_ticks(theme.S(13)):
            cv.create_line(gx, y0, gx, y0 + hh,
                           fill=theme.BAR_TICK if hour % 6 == 0 else theme.BAR_TICK_WEAK)

        gap = theme.S(1)
        labels: list[tuple[float, float, str, str]] = []
        for slot in state["slots"]:
            sx, ex = to_x(slot.start_s), to_x(slot.end_s)
            if ex - sx < 2:
                ex = sx + 2
            if slot.is_class:
                # 上课时段：磨砂白块 + 深色字，是整条里唯一的「实心」
                fill, fg, outline = theme.BAR_FG, theme.GLASS, ""
            else:
                fill, fg = theme.mix(theme.GLASS, theme.BAR_LINE, 0.22), theme.BAR_FG2
                outline = theme.mix(theme.GLASS, theme.BAR_LINE, 0.40)
            # 相邻块之间留 1px 缝，30 分钟的小节也能看出边界
            bx0, bx1 = sx + gap / 2, ex - gap / 2
            cv.create_polygon(rounded_points(bx0, y0, bx1, y0 + hh, theme.S(4)),
                              fill=fill, outline=outline, width=1)
            label = self._fit_slot_text(slot.label(), bx1 - bx0)
            if label:
                labels.append(((bx0 + bx1) / 2, y0 + hh / 2, label, fg))

        # 「现在」指示线：与上面进度条的进度头同一横坐标；先画线再画字，
        # 否则线会横穿正在上的那节课的名称（看着像被划掉）。
        nx = to_x(state["sec"])
        cv.create_line(nx, y0 - theme.S(2), nx, y0 + hh + theme.S(2),
                       fill=theme.BAR_ACCENT, width=theme.S(1.5))
        for cx, cy, text, fg in labels:
            cv.create_text(cx, cy, text=text, fill=fg, font=self.F(9))
