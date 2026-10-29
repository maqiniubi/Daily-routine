"""设置中心：作息表管理、每周周期安排、课程表、倒计时、全局设置。

视觉改版（v1.2.0）：按 Apple 的层级体系重排——
窗口底 → 区块 → 卡片三层明度，导航从 ttk.Notebook 换成自绘分段控件，
主操作一律白色填充，选中态用系统蓝，卡片统一 14dp 圆角。
"""
from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk

from .. import config, palette, theme, win32util
from ..models import (DAY_KEYS, DAY_NAMES, KIND_BREAK, KIND_BY_LABEL, KIND_CLASS, KIND_LABELS,
                      KIND_OTHER, Period, Schedule, fmt_minutes, new_id, parse_time)
from ..power import format_hhmm, parse_hhmm
from ..scheduler import build_slots
from .appearance_tab import AppearanceTab
from .common import FormDialog, ScrollFrame, ask_yes_no, option_menu, show_info
from .countdown_tab import CountdownTab
from .sponsor import show_sponsor
from .widgets import Badge, Button, DayPicker, RoundedBox, Switch, TabBar


def _mk_tree(parent, columns: list[tuple[str, str, int]], height: int = 8) -> tuple[tk.Frame, ttk.Treeview]:
    wrap = tk.Frame(parent, bg=theme.CARD)
    tree = ttk.Treeview(wrap, columns=[c[0] for c in columns], show="headings", selectmode="browse",
                        height=height)
    for key, title, width in columns:
        tree.heading(key, text=title, anchor="w")
        tree.column(key, width=theme.S(width), minwidth=theme.S(48), anchor="w",
                    stretch=(key in ("name", "course")))
    bar = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview, style="Vertical.TScrollbar")
    tree.configure(yscrollcommand=bar.set)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y", padx=(theme.S(2), 0))
    return wrap, tree


def _elide(text: str, limit: int) -> str:
    """超长路径做「中间省略」，保住盘符与文件名，且不会在任意字符处折行。"""
    if len(text) <= limit:
        return text
    head = max(6, (limit - 3) // 2)
    tail = max(6, limit - 3 - head)
    return f"{text[:head]}…{text[-tail:]}"


def _label(parent, text: str, role: str = "body", fg: str | None = None,
           **kw) -> tk.Label:
    bg = kw.pop("bg", parent.cget("bg"))
    return tk.Label(parent, text=text, bg=bg, fg=fg or theme.FG, font=theme.T(role),
                    anchor="w", justify=kw.pop("justify", "left"), **kw)


def _caption(parent, text: str, **kw) -> tk.Label:
    return _label(parent, text, "caption", theme.FG3, **kw)


def _restyle_one(widget) -> None:
    """把单个控件的 bg / fg 换成当前配色里的对应取值。

    bg 与 fg 分开解析角色：白色在浅色主题里既是卡片底色（CARD）又是强调色上的
    前景色（ON_ACCENT），混在一起查表就会张冠李戴——切回深色后白卡片留在深色
    界面上就是这么来的。
    """
    for opt in ("bg", "fg"):
        try:
            cur = widget.cget(opt)
        except (tk.TclError, AttributeError):
            continue
        if not isinstance(cur, str):
            continue
        new = theme.remap(cur, "bg" if opt == "bg" else "fg")
        if new == cur:
            continue
        try:
            widget.configure(**{opt: new})
        except tk.TclError:
            pass


def _restyle_tree(widget, skip=()) -> None:
    """把整棵控件树上「上一轮配色的颜色」换成当前配色。

    只处理 bg / fg 两个选项：其它颜色（悬停、描边、渐变）都在控件的
    _draw() / _render() 里现算，交给它们自己的 restyle() 重画。

    控件**自身**也要换：页签容器（作息表页 / 周视图页……）的底色是直接设在自己
    身上的，只换子控件的话，容器自己永远留着上一轮配色——切回深色后作息表页
    就剩一块深色底。所以先换自身，再递归子控件。

    skip 里的控件整棵跳过（页签由调用方单独处理）。
    """
    _restyle_one(widget)
    try:
        children = widget.winfo_children()
    except tk.TclError:
        return
    for child in children:
        if any(child is item for item in skip):
            continue
        _restyle_one(child)
        painter = getattr(child, "restyle", None)
        if callable(painter):
            try:
                painter()
            except Exception:
                pass
        _restyle_tree(child, skip)      # skip 必须一路传下去，否则只在第一层生效


class _TabHost:
    """TabBar 的 Notebook 兼容层：select() 可传下标或控件。"""

    def __init__(self, bar: TabBar, frames: list[tk.Frame], on_show=None):
        self._bar = bar
        self._frames = frames
        self._on_show = on_show

    def select(self, which=None):
        if which is None:
            return self._frames[self._bar.current()]
        if isinstance(which, int):
            index = which
        else:
            try:
                index = self._frames.index(which)
            except ValueError:
                return None
        self._bar.select(index)
        # 兜底：TabBar 在「下标没变化」时不会回调 on_change，而 tkraise 必须发生，
        # 否则首屏会停在最后 grid 的那一页上。
        try:
            self._frames[index].tkraise()
        except tk.TclError:
            return None
        if self._on_show is not None:
            try:
                self._on_show(index)      # 切页时补上这一页欠下的换色
            except Exception:
                pass
        return self._frames[index]

    def add(self, *_a, **_k) -> None:      # 兼容旧的 nb.add() 调用
        return None


class MainWindow(tk.Toplevel):
    TAB_TITLES = ("作息时间表", "每周周期", "课程表", "倒计时", "设置", "外观")

    def __init__(self, ctl):
        super().__init__(ctl.root)
        self.ctl = ctl
        self.withdraw()
        self.title(f"{config.APP_TITLE} · 设置中心")
        self.configure(bg=theme.BG)
        self.minsize(min(theme.S(860), self.winfo_screenwidth() - theme.S(60)),
                     min(theme.S(520), self.winfo_screenheight() - theme.S(160)))
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self.hide)

        self._build()
        self._place()
        self.apply_window_alpha()
        self.deiconify()
        self.lift()
        self.after(60, lambda: win32util.set_dark_titlebar(win32util.hwnd_of(self)))
        self.after(120, self.focus_force)

    def apply_window_alpha(self) -> None:
        """窗口不透明度（外观页可调）：只影响这一个窗口，悬浮条另有自己的 alpha。"""
        ui_alpha, _bar = palette.alphas(self.ctl.data.settings)
        try:
            self.attributes("-alpha", ui_alpha)
        except tk.TclError:
            pass

    def _place(self) -> None:
        """在悬浮条下方居中显示，并保证完整落在屏幕内。"""
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        bar = self.ctl.topbar.height()
        w = min(theme.S(1020), sw - theme.S(40))
        h = min(theme.S(700), sh - bar - theme.S(38))
        x = max(0, (sw - w) // 2)
        y = min(bar + theme.S(12), max(0, sh - h - theme.S(8)))
        self.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")

    # ---------------- 布局 ----------------
    def _build(self) -> None:
        # ---- 顶栏 ----
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill="x", padx=theme.P(6), pady=(theme.P(5), theme.P(3)))

        titles = tk.Frame(head, bg=theme.BG)
        titles.pack(side="left")
        title_row = tk.Frame(titles, bg=theme.BG)
        title_row.pack(anchor="w")
        _label(title_row, config.APP_TITLE, "display", bg=theme.BG).pack(side="left")
        Badge(title_row, "永恒", command=self.ctl.show_about, bg=theme.BG,
              height=22).pack(side="left", padx=(theme.S(10), 0))
        _caption(titles, f"v{config.APP_VERSION}　常驻置顶 · 托盘运行 · 作者 永恒", bg=theme.BG).pack(
            anchor="w", pady=(theme.S(2), 0))

        Button(head, "×", self.hide, kind="ghost", width=theme.S(34), radius=9).pack(side="right")
        Button(head, "❤ 赞赏支持", self._show_sponsor, kind="primary", height=32).pack(
            side="right", padx=(theme.S(8), theme.S(10)))
        Button(head, "导出", self.export_data, kind="ghost", height=32).pack(side="right")
        Button(head, "导入", self.import_data, kind="ghost", height=32).pack(side="right")

        tk.Frame(self, bg=theme.LINE, height=1).pack(fill="x", padx=theme.P(6))

        # ---- 底部状态栏（先占位，避免被内容挤掉）----
        # 数据文件路径已经在「设置」页的说明区展示，这里只留一行瞬时提示，
        # 省下的高度留给两栏卡片，避免设置项多了以后右侧被挤出滚动。
        foot = tk.Frame(self, bg=theme.BG)
        foot.pack(fill="x", side="bottom", padx=theme.P(6), pady=(0, theme.P(2)))
        self.lbl_tip = tk.Label(foot, text="", bg=theme.BG, fg=theme.FG2, font=theme.T("caption"),
                                anchor="w")
        self.lbl_tip.pack(side="left")

        # ---- 分段导航 ----
        self.nav = tk.Frame(self, bg=theme.BG)
        self.nav.pack(fill="x", padx=theme.P(6), pady=(theme.P(3), 0))
        self.tabbar = TabBar(self.nav, list(self.TAB_TITLES), self._on_tab_pick, bg=theme.BG)
        self.tabbar.pack(anchor="w")

        # ---- 内容区 ----
        self.content = tk.Frame(self, bg=theme.BG)
        self.content.pack(fill="both", expand=True, padx=theme.P(5), pady=(theme.P(3), theme.P(3)))
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        self.tab_sched = SchedulesTab(self.content, self.ctl)
        self.tab_week = WeekTab(self.content, self.ctl)
        self.tab_course = CoursesTab(self.content, self.ctl)
        self.tab_countdown = CountdownTab(self.content, self.ctl)
        self.tab_settings = SettingsTab(self.content, self.ctl)
        self.tab_appearance = AppearanceTab(self.content, self.ctl)

        for tab in (self.tab_sched, self.tab_week, self.tab_course,
                    self.tab_countdown, self.tab_settings, self.tab_appearance):
            tab.grid(row=0, column=0, sticky="nsew")

        self.tab_sched.tkraise()        # 首屏必须是第一页，grid 的后建者会在最上层

        self.nb = _TabHost(self.tabbar, [self.tab_sched, self.tab_week, self.tab_course,
                                        self.tab_countdown, self.tab_settings,
                                        self.tab_appearance],
                           on_show=self._flush_pending_restyle)
        # 换肤时先只换可见页签，其余记在这里，切过去时再补
        self._pending_restyle: set[int] = set()
        self._table_style_dirty = False
        self.after(80, self._init_first_tab)

    # ---------------- 行为 ----------------
    def _init_first_tab(self) -> None:
        """首帧把胶囊高亮定位到第 0 页。

        别抢用户的选择：这 80 毫秒里如果用户已经切过页签，就保持不动
        （以前是无条件 select(0)，会把用户刚点开的页签弹回第一页）。
        """
        try:
            if self.tabbar.current() != 0:
                return
            self.tabbar.select(0, animated=False)
        except tk.TclError:
            pass

    def _tabs(self) -> tuple:
        return (self.tab_sched, self.tab_week, self.tab_course,
                self.tab_countdown, self.tab_settings, self.tab_appearance)

    def _on_tab_pick(self, index: int) -> None:
        tabs = self._tabs()
        try:
            tabs[index].tkraise()
        except (tk.TclError, IndexError):
            return
        self._flush_pending_restyle(index)     # 这一页若欠着换色，此刻补上
        if tabs[index] is self.tab_week:
            self.after(40, self.tab_week.reveal_today)

    def _on_tab_changed(self, _event=None) -> None:
        self._on_tab_pick(self.tabbar.current())

    def _show_sponsor(self) -> None:
        show_sponsor(self, self.ctl)

    def toast_tip(self, text: str) -> None:
        self.lbl_tip.configure(text=text)
        self.after(2600, lambda: self.lbl_tip.configure(text=""))

    def hide(self) -> None:
        """关闭设置中心只是隐藏，顶部悬浮条继续常驻运行。"""
        self.withdraw()

    def refresh_all(self) -> None:
        for tab in self._tabs():
            tab.refresh()

    def restyle(self) -> None:
        """配色变化后就地重着色（不销毁窗口）。

        为什么不用「销毁重建」：外观页的取色按钮就在这棵树里，销毁会让正在
        被点击的控件在回调还没返回时消失，Tk 会抛 callback 异常并弹出 Win32 错误框。
        所以这里改成「把上一轮配色里的颜色整体换成新色」，自绘部件各自重画。

        只处理**当前可见的页签**：六个页签加起来几百个控件，逐个 configure
        就要四十多毫秒，还要连带触发几百次重绘；而看不见的页签根本不用换，
        等切过去时再补（见 _on_tab_pick）。
        """
        try:
            self.configure(bg=theme.BG)
        except tk.TclError:
            return
        tabs = self._tabs()
        current = self.tabbar.current()
        # 整棵窗口树都换（标题栏、导航条、底栏都在这里），页签单独处理：
        # 看不见的页签先欠着，切过去时再补。
        _restyle_tree(self, skip=tabs)
        for index, tab in enumerate(tabs):
            if index == current:
                _restyle_tree(tab)
                self._pending_restyle.discard(index)
            else:
                self._pending_restyle.add(index)
        # 表格样式（ttk Treeview）换配色时不刷：3 个表格重新派生要二十多毫秒，
        # 而表格页看不见。等切过去时再补（见 _flush_pending_restyle）。
        self._table_style_dirty = True
        if current in (0, 2):            # 当前就在表格页，样式得立刻跟上
            self._refresh_table_style()
        self.apply_window_alpha()
        try:
            self.tab_appearance.refresh()
        except Exception:
            pass

    def _refresh_table_style(self) -> None:
        """刷新 ttk 表格样式（Treeview 的颜色只由样式驱动）。"""
        try:
            from .common import init_style

            init_style(self.ctl.root, groups=("table",))
            self._table_style_dirty = False
        except Exception:
            pass

    def _flush_pending_restyle(self, index: int) -> None:
        """切到某页时，把这一页欠下的换色补上。"""
        if index in (0, 2) and self._table_style_dirty:
            self._refresh_table_style()
        try:
            tab = self._tabs()[index]
        except IndexError:
            return
        if index not in self._pending_restyle:
            # 这一页没欠账，但它自身的底色仍可能停在上一轮配色（页签容器不在
            # 子控件的遍历范围里），单独修一次，代价只有一个控件。
            _restyle_one(tab)
            return
        self._pending_restyle.discard(index)
        try:
            _restyle_tree(tab)
        except Exception:
            pass

    def export_data(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, title="导出作息时间表", defaultextension=".json",
            initialfile="classbell_schedule.json", filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            self.ctl.store.export_to(path)
            self.toast_tip(f"已导出到 {os.path.basename(path)}")
        except Exception as exc:
            show_info(self, "导出失败", str(exc))

    def import_data(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="导入作息时间表", filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        if not ask_yes_no(self, "确认导入", "导入将覆盖当前全部作息表、周期安排与课程表，是否继续？"):
            return
        try:
            self.ctl.import_data(path)
            self.refresh_all()
            self.toast_tip("导入成功")
        except Exception as exc:
            show_info(self, "导入失败", str(exc))


class SchedulesTab(tk.Frame):
    @property
    def data(self):
        return self.ctl.data

    def __init__(self, parent, ctl):
        super().__init__(parent, bg=theme.BG)
        self.ctl = ctl
        self._current_id: str | None = None
        self._reloading = False        # 重建列表期间屏蔽 <<ListboxSelect>>，避免行号错位

        wrap = tk.Frame(self, bg=theme.BG)
        wrap.pack(fill="both", expand=True)

        # 左：作息表列表（卡片）
        left_box = RoundedBox(wrap, radius=14, fill=theme.CARD, pad=0)
        left_box.configure(width=theme.S(198))
        left_box.pack(side="left", fill="y", padx=(0, theme.P(3)))
        left_box.pack_propagate(False)
        left = tk.Frame(left_box.body, bg=theme.CARD, padx=theme.P(3), pady=theme.P(3))
        left.pack(fill="both", expand=True)

        _caption(left, "作息表", bg=theme.CARD).pack(fill="x", pady=(0, theme.S(6)))
        self.listbox = tk.Listbox(left, bg=theme.CARD, fg=theme.FG, font=theme.T("body"),
                                  selectbackground=theme.CARD_HOVER, selectforeground=theme.FG,
                                  bd=0, highlightthickness=0, activestyle="none",
                                  width=16, exportselection=False)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_pick)

        btns = tk.Frame(left, bg=theme.CARD)
        btns.pack(fill="x", pady=(theme.S(8), 0))
        Button(btns, "新建", self.add_schedule, kind="secondary",
               width=theme.S(58), height=28, bg=theme.CARD).pack(side="left")
        Button(btns, "复制", self.duplicate_schedule, kind="ghost",
               width=theme.S(58), height=28, bg=theme.CARD).pack(side="left", padx=theme.S(4))
        more = tk.Frame(left, bg=theme.CARD)
        more.pack(fill="x", pady=(theme.S(4), 0))
        Button(more, "改名", self.rename_schedule, kind="ghost",
               width=theme.S(58), height=28, bg=theme.CARD).pack(side="left")
        Button(more, "删除", self.delete_schedule, kind="ghost",
               width=theme.S(58), height=28, bg=theme.CARD).pack(side="left", padx=theme.S(4))

        # 右：时段表（卡片）
        right_box = RoundedBox(wrap, radius=14, fill=theme.CARD, pad=0)
        right_box.pack(side="left", fill="both", expand=True)
        right = tk.Frame(right_box.body, bg=theme.CARD, padx=theme.P(4), pady=theme.P(3))
        right.pack(fill="both", expand=True)

        head = tk.Frame(right, bg=theme.CARD)
        head.pack(fill="x", pady=(0, theme.S(10)))
        self.lbl_title = _label(head, "", "headline", bg=theme.CARD)
        self.lbl_title.pack(side="left")
        self.lbl_meta = tk.Label(head, text="", bg=theme.CARD, fg=theme.FG3, font=theme.T("caption"))
        self.lbl_meta.pack(side="left", padx=(theme.S(10), 0), pady=(theme.S(3), 0))

        Button(head, "+ 添加时段", self.add_period, kind="primary", bg=theme.CARD).pack(side="right")
        Button(head, "编辑", self.edit_period, kind="secondary", bg=theme.CARD,
               width=theme.S(56)).pack(side="right", padx=(0, theme.S(6)))
        Button(head, "删除", self.delete_period, kind="ghost", bg=theme.CARD,
               width=theme.S(56)).pack(side="right")

        self.tree_wrap, self.tree = _mk_tree(right, [
            ("idx", "#", 46), ("name", "时段名称", 200), ("start", "开始", 90),
            ("end", "结束", 90), ("dur", "时长", 90), ("kind", "类型", 80),
        ], height=9)
        self.tree_wrap.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_period())

        self.refresh()

    # ---------- 数据 ----------
    def current_schedule(self) -> Schedule:
        sched = self.data.get_schedule(self._current_id or "") or self.data.schedules[0]
        self._current_id = sched.id
        return sched

    def refresh(self) -> None:
        """左栏列表 + 右侧表格一起重建。任何增删改之后都必须走这里。"""
        self._reload_list()
        self._fill_tree()

    def _reload_list(self) -> None:
        """按数据重建作息表列表，选中态按 id 还原。

        以前这里用「行号」维护选中，删除后行号会整体前移：列表还留着旧条目、
        点一下就 IndexError。所以一律用 id 对齐。
        """
        self._reloading = True
        try:
            self.listbox.delete(0, "end")
            for s in self.data.schedules:
                self.listbox.insert("end", f"  {s.name}")
            if self.data.get_schedule(self._current_id or "") is None:
                # 当前表被删了（或首次进入）：退回第一张
                self._current_id = self.data.schedules[0].id if self.data.schedules else None
            ids = [s.id for s in self.data.schedules]
            if self._current_id in ids:
                index = ids.index(self._current_id)
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(index)
                self.listbox.see(index)          # 新建在末尾时滚进可视区
        finally:
            self._reloading = False

    def _on_pick(self, _event=None) -> None:
        if self._reloading:
            return
        sel = self.listbox.curselection()
        if not sel:
            return
        # 列表事件可能滞后于数据变化，越界就忽略，绝不让索引直接打数据
        if sel[0] >= len(self.data.schedules):
            self._reload_list()
            return
        sched = self.data.schedules[sel[0]]
        if sched.id == self._current_id:
            return
        self._current_id = sched.id
        self._fill_tree()

    def _fill_tree(self) -> None:
        sched = self.current_schedule()
        self.tree.delete(*self.tree.get_children())
        used: set[str] = set()
        for i, p in enumerate(sched.sorted_periods(), start=1):
            if p.id in used:
                # 手改过 JSON 的重复 id：就地换新，否则 Treeview 的 iid 冲突会抛异常
                p.id = new_id("p")
            used.add(p.id)
            self.tree.insert("", "end", iid=p.id, values=(
                i, p.name, p.start, p.end, f"{p.duration_min()} 分钟", KIND_LABELS.get(p.kind, "其它")))
        self.lbl_title.configure(text=sched.name)
        if sched.periods:
            total = sum(p.duration_min() for p in sched.periods)
            meta = f"{len(sched.periods)} 个时段 · 共 {total // 60} 小时 {total % 60} 分"
        else:
            meta = "还没有时段 · 点右上「+ 添加时段」开始录入"
        self.lbl_meta.configure(text=meta)
        self.tree.yview_moveto(0)     # 重填后回到表头，否则会停在旧滚动位上

    def _commit(self, tip: str = "") -> None:
        """一次改动的统一收口：落盘 → 左栏/右表重建 → 关联页面与悬浮条同步。"""
        self.ctl.save_data()
        self.refresh()
        self.ctl.main_window_refresh_week()      # 周周期里的作息表名 / 摘要
        self.ctl.main_window_refresh_course()    # 课程表按当天作息表列时段
        self.ctl.topbar.refresh()
        if tip:
            win = self.winfo_toplevel()
            if hasattr(win, "toast_tip"):
                win.toast_tip(tip)

    def _unique_name(self, base: str) -> str:
        """名称必须唯一：周周期是按名字反查 id 的，重名会指错作息表。"""
        names = set(self.data.schedule_names())
        if base not in names:
            return base
        for i in range(2, 100):
            cand = f"{base} {i}"
            if cand not in names:
                return cand
        return base

    # ---------- 作息表 ----------
    def add_schedule(self) -> None:
        names = self.data.schedule_names()
        cur = self.current_schedule().name
        default_from = cur if cur in names else "空白"

        def ok(values):
            name = values.get("name", "").strip()
            if not name:
                raise ValueError("名称不能为空")
            if name in names:
                raise ValueError("已存在同名作息表")
            sched = Schedule(id=new_id("s"), name=name, periods=[])
            src_label = values.get("from", "空白")
            if src_label in names:
                # 一路复制时段，新表立刻有内容，不会出现「建完是空表」的错觉
                src = self.data.schedules[names.index(src_label)]
                sched.periods = [Period(new_id("p"), p.name, p.start, p.end, p.kind)
                                 for p in src.periods]
            self.data.schedules.append(sched)
            self._current_id = sched.id
            self._commit(f"已新建作息表「{name}」")

        FormDialog(self, "新建作息表", [
            {"key": "name", "label": "名称", "default": "新作息表"},
            {"key": "from", "label": "复制自", "kind": "combo",
             "options": ["空白"] + names, "default": default_from},
        ], hint="选「复制自」可连时段一起建，选「空白」从零开始。",
           on_submit=ok)

    def duplicate_schedule(self) -> None:
        src = self.current_schedule()
        sched = Schedule(id=new_id("s"), name=self._unique_name(f"{src.name} 副本"),
                         periods=[Period(new_id("p"), p.name, p.start, p.end, p.kind)
                                  for p in src.periods])
        self.data.schedules.append(sched)
        self._current_id = sched.id
        self._commit(f"已复制为「{sched.name}」")

    def rename_schedule(self) -> None:
        sched = self.current_schedule()

        def ok(values):
            name = values.get("name", "").strip()
            if not name:
                raise ValueError("名称不能为空")
            others = [s.name for s in self.data.schedules if s.id != sched.id]
            if name in others:
                raise ValueError("已存在同名作息表")
            sched.name = name
            self._commit(f"已改名为「{name}」")

        FormDialog(self, "重命名作息表", [{"key": "name", "label": "名称", "default": sched.name}],
                   on_submit=ok)

    def delete_schedule(self) -> None:
        if len(self.data.schedules) <= 1:
            show_info(self, "无法删除", "至少需要保留一张作息表。")
            return
        sched = self.current_schedule()
        used = [DAY_NAMES[DAY_KEYS.index(d)] for d, sid in self.data.week.items() if sid == sched.id]
        msg = f"确定删除作息表「{sched.name}」？"
        if used:
            msg += f"\n\n以下日期正在使用它，将自动改用其它作息表：{'、'.join(used)}"
        if not ask_yes_no(self, "删除作息表", msg):
            return
        index = next((i for i, s in enumerate(self.data.schedules) if s.id == sched.id), 0)
        self.data.schedules = [s for s in self.data.schedules if s.id != sched.id]
        fallback = self.data.schedules[min(index, len(self.data.schedules) - 1)].id
        for day in DAY_KEYS:
            if self.data.week.get(day) == sched.id:
                self.data.week[day] = fallback
        self.data.cleanup_courses()
        self._current_id = fallback
        self._commit(f"已删除作息表「{sched.name}」")

    # ---------- 时段 ----------
    def _selected_period(self) -> Period | None:
        sel = self.tree.selection()
        if not sel:
            return None
        sched = self.current_schedule()
        for p in sched.periods:
            if p.id == sel[0]:
                return p
        return None

    def add_period(self) -> None:
        sched = self.current_schedule()
        default_start = "08:00"
        if sched.periods:
            last = sched.sorted_periods()[-1]
            default_start = fmt_minutes(parse_time(last.end) + 10)

        def ok(values):
            p = Period(id=new_id("p"), name=values["name"], start=values["start"],
                       end=values["end"], kind=KIND_BY_LABEL.get(values["kind"], KIND_CLASS))
            p.validate()
            sched.periods.append(p)
            self._commit("已添加时段")

        FormDialog(self, "添加时段", [
            {"key": "name", "label": "名称", "default": "第一节"},
            {"key": "start", "label": "开始 (HH:MM)", "default": default_start},
            {"key": "end", "label": "结束 (HH:MM)", "default": fmt_minutes(parse_time(default_start) + 45)},
            {"key": "kind", "label": "类型", "kind": "combo",
             "options": [KIND_LABELS[KIND_CLASS], KIND_LABELS[KIND_BREAK], KIND_LABELS[KIND_OTHER]],
             "default": KIND_LABELS[KIND_CLASS]},
        ], on_submit=ok)

    def edit_period(self) -> None:
        p = self._selected_period()
        if p is None:
            show_info(self, "未选择", "请先在列表中选择一个时段。")
            return

        def ok(values):
            name, start, end = values["name"], values["start"], values["end"]
            kind = KIND_BY_LABEL.get(values["kind"], p.kind)
            probe = Period(id=p.id, name=name, start=start, end=end, kind=kind)
            probe.validate()
            p.name, p.start, p.end, p.kind = name, start, end, kind
            self._commit("已保存修改")

        FormDialog(self, "编辑时段", [
            {"key": "name", "label": "名称", "default": p.name},
            {"key": "start", "label": "开始 (HH:MM)", "default": p.start},
            {"key": "end", "label": "结束 (HH:MM)", "default": p.end},
            {"key": "kind", "label": "类型", "kind": "combo",
             "options": [KIND_LABELS[KIND_CLASS], KIND_LABELS[KIND_BREAK], KIND_LABELS[KIND_OTHER]],
             "default": KIND_LABELS.get(p.kind, KIND_LABELS[KIND_CLASS])},
        ], on_submit=ok)

    def delete_period(self) -> None:
        p = self._selected_period()
        if p is None:
            show_info(self, "未选择", "请先在列表中选择一个时段。")
            return
        if not ask_yes_no(self, "删除时段", f"确定删除时段「{p.name}」？相关课程记录会一并清理。"):
            return
        sched = self.current_schedule()
        sched.periods = [x for x in sched.periods if x.id != p.id]
        self.data.cleanup_courses()
        self._commit("已删除时段")


class WeekTab(tk.Frame):
    @property
    def data(self):
        return self.ctl.data

    def __init__(self, parent, ctl):
        super().__init__(parent, bg=theme.BG)
        self.ctl = ctl
        self._vars: dict[str, tk.StringVar] = {}
        self._row: dict[str, tuple] = {}

        wrap = tk.Frame(self, bg=theme.BG)
        wrap.pack(fill="both", expand=True)

        _label(wrap, "每周周期", "headline").pack(fill="x")
        _label(wrap, "为每一天指定采用的作息表。悬浮条与提醒会按当天日期自动切换。",
               "caption", theme.FG3).pack(fill="x", pady=(theme.S(3), theme.P(3)))

        self.scroll = ScrollFrame(wrap, bg=theme.BG)
        self.scroll.pack(fill="both", expand=True)

        box = RoundedBox(self.scroll.body, radius=14, fill=theme.CARD, pad=0)
        box.pack(fill="x", pady=(0, theme.P(3)))
        self.panel = tk.Frame(box.body, bg=theme.CARD, padx=theme.P(4), pady=theme.P(2))
        self.panel.pack(fill="both", expand=True)

        self.rows = tk.Frame(self.panel, bg=theme.CARD)
        self.rows.pack(fill="x")
        self.rows.columnconfigure(1, weight=0)
        self.rows.columnconfigure(2, weight=1)

        for i, day in enumerate(DAY_KEYS):
            if i:
                tk.Frame(self.rows, bg=theme.LINE, height=1).grid(
                    row=i * 2 - 1, column=0, columnspan=3, sticky="ew", pady=theme.S(1))
            base = i * 2
            tk.Label(self.rows, text=DAY_NAMES[i], bg=theme.CARD, fg=theme.FG,
                     font=theme.T("body-bold"), width=5, anchor="w").grid(
                row=base, column=0, sticky="w", pady=theme.S(7))
            var = tk.StringVar()
            self._vars[day] = var
            picker = option_menu(self.rows, var, self._names, lambda v, d=day: self._apply(d),
                                 bg=theme.CARD, fill=theme.CARD_HOVER)
            picker.grid(row=base, column=1, sticky="w", padx=(theme.S(8), theme.P(4)), pady=theme.S(7))
            lbl = tk.Label(self.rows, text="", bg=theme.CARD, fg=theme.FG3, font=theme.T("caption"),
                           anchor="w")
            lbl.grid(row=base, column=2, sticky="w", pady=theme.S(7))
            setattr(self, f"_sum_{day}", lbl)
            self._row[day] = (picker, lbl)

        self.tree = None
        self.refresh()

    def _names(self) -> list[str]:
        return self.data.schedule_names()

    def reveal_today(self, retry: bool = True) -> None:
        """内容放不下时，把「今天」那一行滚进可视区。"""
        self.update_idletasks()
        self.scroll._refresh_bar()
        if not self.scroll._bar_shown:
            if retry:
                # 首次切页时布局可能未定，稍后重试一次
                self.after(140, lambda: self.reveal_today(False))
            return
        day = DAY_KEYS[datetime.now().weekday()]
        row = self._row.get(day)
        if row:
            self.scroll.scroll_to_widget(row[0])

    def refresh(self) -> None:
        for day in DAY_KEYS:
            self._vars[day].set(self.data.schedule_for_day(day).name)
            getattr(self, f"_sum_{day}").configure(text=self.data.day_summary(day))

    def _apply(self, day: str) -> None:
        name = self._vars[day].get()
        names = self.data.schedule_names()
        if name in names:
            self.data.week[day] = self.data.schedules[names.index(name)].id
            self.ctl.save_data()
            getattr(self, f"_sum_{day}").configure(text=self.data.day_summary(day))
            self.ctl.topbar.refresh()
            self.ctl.main_window_refresh_course()


class CoursesTab(tk.Frame):
    @property
    def data(self):
        return self.ctl.data

    def __init__(self, parent, ctl):
        super().__init__(parent, bg=theme.BG)
        self.ctl = ctl
        self._day = tk.StringVar(value=DAY_NAMES[0])

        wrap = tk.Frame(self, bg=theme.BG)
        wrap.pack(fill="both", expand=True)

        head = tk.Frame(wrap, bg=theme.BG)
        head.pack(fill="x", pady=(0, theme.P(2)))
        _label(head, "课程表", "headline").pack(side="left")
        self.combo = option_menu(head, self._day, lambda: DAY_NAMES, lambda v: self.refresh(),
                                 bg=theme.BG, width_px=theme.S(104))
        self.combo.pack(side="left", padx=(theme.P(3), theme.S(8)))

        Button(head, "+ 设置课程", self.edit_course, kind="primary").pack(side="right")
        Button(head, "清空当天", self.clear_day, kind="ghost").pack(side="right", padx=(0, theme.S(4)))
        Button(head, "复制到…", self.copy_day, kind="ghost").pack(side="right")

        box = RoundedBox(wrap, radius=14, fill=theme.CARD, pad=0)
        box.pack(fill="both", expand=True)
        inner = tk.Frame(box.body, bg=theme.CARD, padx=theme.P(3), pady=theme.P(2))
        inner.pack(fill="both", expand=True)

        self.lbl_hint = tk.Label(inner, text="", bg=theme.CARD, fg=theme.FG3, font=theme.T("caption"),
                                 anchor="w", justify="left")
        self.lbl_hint.pack(fill="x", pady=(0, theme.S(8)))

        self.tree_wrap, self.tree = _mk_tree(inner, [
            ("time", "时间", 150), ("name", "时段", 150), ("kind", "类型", 80), ("course", "课程", 240),
        ], height=10)
        self.tree_wrap.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_course())

        self.refresh()

    def day_key(self) -> str:
        return DAY_KEYS[DAY_NAMES.index(self._day.get())]

    def refresh(self) -> None:
        key = self.day_key()
        sched = self.data.schedule_for_day(key)
        courses = self.data.courses_for_day(key)
        self.tree.delete(*self.tree.get_children())
        for p in sched.sorted_periods():
            self.tree.insert("", "end", iid=p.id, values=(
                f"{p.start} - {p.end}", p.name, KIND_LABELS.get(p.kind, "其它"), courses.get(p.id, "")))
        self.lbl_hint.configure(
            text=f"当前采用「{sched.name}」。双击任意行录入课程，上课提醒会说「到上数学课时间了！」")
        self.tree.yview_moveto(0)

    def _selected(self) -> tuple[Period, str] | None:
        sel = self.tree.selection()
        if not sel:
            return None
        key = self.day_key()
        period = next((p for p in self.data.schedule_for_day(key).periods if p.id == sel[0]), None)
        if period is None:
            return None
        return period, self.data.courses_for_day(key).get(period.id, "")

    def edit_course(self) -> None:
        picked = self._selected()
        if picked is None:
            show_info(self, "未选择", "请先选择一行时段。")
            return
        period, current = picked
        key = self.day_key()

        def ok(values):
            name = values.get("course", "").strip()
            table = self.data.courses_for_day(key)
            if name:
                table[period.id] = name
            else:
                table.pop(period.id, None)
            self.ctl.save_data()
            self.refresh()
            self.ctl.topbar.refresh()

        FormDialog(self, f"设置课程 · {DAY_NAMES[DAY_KEYS.index(key)]} · {period.name}", [
            {"key": "course", "label": "课程名称", "default": current, "kind": "entry"},
        ], hint="留空表示该时段没有课程（提醒将使用时段名称）。", on_submit=ok)

    def clear_day(self) -> None:
        key = self.day_key()
        if not ask_yes_no(self, "清空课程", f"确定清空{DAY_NAMES[DAY_KEYS.index(key)]}的全部课程？"):
            return
        self.data.courses[key] = {}
        self.ctl.save_data()
        self.refresh()
        self.ctl.topbar.refresh()

    def copy_day(self) -> None:
        src_name = self._day.get()
        options = [d for d in DAY_NAMES if d != src_name]

        def ok(values):
            target = values["to"]
            src = self.data.courses_for_day(DAY_KEYS[DAY_NAMES.index(src_name)])
            dst_key = DAY_KEYS[DAY_NAMES.index(target)]
            valid = {p.id for p in self.data.schedule_for_day(dst_key).periods}
            table = self.data.courses_for_day(dst_key)
            for pid, name in src.items():
                if pid in valid:
                    table[pid] = name
            self.ctl.save_data()
            self.refresh()
            self.ctl.topbar.refresh()

        FormDialog(self, "复制课程表", [{"key": "to", "label": "复制到", "kind": "combo",
                                        "options": options, "default": options[0]}],
                   hint=f"把{src_name}的课程复制到目标星期（同名时段才会生效）。", on_submit=ok)


class SettingsTab(tk.Frame):
    @property
    def data(self):
        return self.ctl.data

    def __init__(self, parent, ctl):
        super().__init__(parent, bg=theme.BG)
        self.ctl = ctl
        self._loading = True

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

        self.v_remind = tk.BooleanVar()
        self.v_end = tk.BooleanVar()
        self.v_24h = tk.BooleanVar()
        self.v_slot = tk.BooleanVar()
        self.v_auto = tk.BooleanVar()
        self.v_secs = tk.IntVar()
        self.v_font = tk.DoubleVar()
        self.v_guard = tk.IntVar()
        self.v_course_h = tk.IntVar()
        self.v_through = tk.BooleanVar()
        self.v_sd_on = tk.BooleanVar()
        self.v_sd_time = tk.StringVar()

        self._section(left, "时段提醒")
        self._switch(left, "到达作息节点时弹出提醒", self.v_remind, self._apply_remind)
        self._switch(left, "课程结束时提醒「到下课时间了！」", self.v_end, self._apply_remind)
        self._spin(left, "气泡停留时间（秒）", self.v_secs, 2, 30, 1, self._apply_remind)

        self._section(left, "桌面悬浮条")
        self._switch(left, "显示 24 小时进度条", self.v_24h, self._apply_ui)
        self._switch(left, "显示今日时段条", self.v_slot, self._apply_ui)
        self._spin(left, "文字缩放（0.8 ~ 1.4）", self.v_font, 0.8, 1.4, 0.1, self._apply_ui, fmt="{:.1f}")
        self._spin(left, "课程名称区域高度（28 ~ 96）", self.v_course_h, 28, 96, 2, self._apply_ui)
        tk.Label(left, text="配色与通透度在「外观」页调整", bg=theme.CARD, fg=theme.FG3,
                 font=theme.T("caption"), anchor="w").pack(fill="x", pady=(0, theme.S(1)))

        self._section(right, "系统与交互")
        self._switch(right, "开机自动启动", self.v_auto, self._apply_autostart)
        self._switch(right, "鼠标穿透（只有本窗口与赞赏面板可点）", self.v_through, self._apply_ui)
        self._spin(right, "置顶守护间隔（毫秒）", self.v_guard, 500, 5000, 100, self._apply_ui)

        self._section(right, "定时关机")
        self._switch(right, "到点自动关闭电脑", self.v_sd_on, self._apply_shutdown)
        self._time(right, "关机时间（24 小时制）", self.v_sd_time, self._apply_shutdown)
        days_row = tk.Frame(right, bg=theme.CARD)
        days_row.pack(fill="x", pady=theme.S(2))
        tk.Label(days_row, text="生效星期", bg=theme.CARD, fg=theme.FG, font=theme.T("body"),
                 anchor="w").pack(side="left", fill="x", expand=True)
        self.days = DayPicker(days_row, on_change=self._apply_shutdown, bg=theme.CARD)
        self.days.pack(side="right")
        self.lbl_sd = tk.Label(right, text="", bg=theme.CARD, fg=theme.FG3,
                               font=theme.T("caption"), anchor="w", justify="left",
                               wraplength=theme.S(420))
        self.lbl_sd.pack(fill="x", pady=(theme.S(1), 0))

        row = tk.Frame(right, bg=theme.CARD)
        row.pack(fill="x", pady=(theme.P(2), 0))
        Button(row, "打开数据目录", self._open_dir, kind="secondary", bg=theme.CARD,
               width=theme.S(100)).pack(side="left")
        Button(row, "立即校准", self._recalibrate, kind="ghost", bg=theme.CARD,
               width=theme.S(78)).pack(side="left", padx=theme.S(4))
        Button(row, "恢复默认", self._reset, kind="ghost", bg=theme.CARD,
               width=theme.S(78)).pack(side="left")

        self._section(right, "使用说明")
        self.lbl_state = tk.Label(right, text="", bg=theme.CARD, fg=theme.FG3, font=theme.T("subhead"),
                                  anchor="w", justify="left", wraplength=theme.S(420))
        self.lbl_state.pack(fill="x", pady=(theme.S(1), 0))
        # 路径单独一行并做「中间省略」，避免长路径在任意字符处折行（config.jso\nn 那种）
        self.lbl_path = tk.Label(right, text="", bg=theme.CARD, fg=theme.FG3, font=theme.T("caption"),
                                 anchor="w")
        self.lbl_path.pack(fill="x", pady=(theme.S(3), 0))

        self._section(right, "关于")
        about = tk.Frame(right, bg=theme.CARD)
        about.pack(fill="x")
        Badge(about, "永恒", command=self.ctl.show_about, bg=theme.CARD,
              height=22).pack(side="left", padx=(0, theme.S(9)))
        tk.Label(about, text=f"{config.APP_TITLE}　v{config.APP_VERSION}", bg=theme.CARD,
                 fg=theme.FG, font=theme.T("body-bold"), anchor="w").pack(side="left")
        Button(about, "❤ 赞赏支持", self._show_sponsor, kind="secondary", bg=theme.CARD,
               height=28).pack(side="right")

        self._loading = False
        self.refresh()

    # ---------- 组件 ----------
    def _section(self, parent, title: str) -> None:
        holder = tk.Frame(parent, bg=theme.CARD)
        holder.pack(fill="x", pady=(theme.P(1), theme.S(1)))
        tk.Label(holder, text=title, bg=theme.CARD, fg=theme.FG2, font=theme.T("caption"),
                 anchor="w").pack(fill="x")

    def _switch(self, parent, text: str, var, command) -> None:
        row = tk.Frame(parent, bg=theme.CARD)
        row.pack(fill="x", pady=theme.S(1))
        tk.Label(row, text=text, bg=theme.CARD, fg=theme.FG, font=theme.T("body"), anchor="w",
                 justify="left", wraplength=theme.S(300)).pack(side="left", fill="x", expand=True)

        def on_toggle(value: bool) -> None:
            var.set(value)
            command()

        sw = Switch(row, bool(var.get()), on_toggle, bg=theme.CARD)
        sw.pack(side="right", padx=(theme.S(8), 0))
        var.trace_add("write", lambda *_: sw.set(bool(var.get())))
        setattr(self, f"_sw_{id(var)}", sw)

    def _spin(self, parent, text: str, var, lo, hi, step, command, fmt: str = "{}") -> None:
        row = tk.Frame(parent, bg=theme.CARD)
        row.pack(fill="x", pady=theme.S(2))
        tk.Label(row, text=text, bg=theme.CARD, fg=theme.FG, font=theme.T("body"), anchor="w").pack(
            side="left", fill="x", expand=True)
        decimals = 2 if fmt == "{:.2f}" else (1 if fmt == "{:.1f}" else 0)
        sp = ttk.Spinbox(row, from_=lo, to=hi, increment=step, textvariable=var, width=7,
                         command=command, format=f"%.{decimals}f")
        sp.pack(side="right")
        sp.bind("<FocusOut>", lambda e: command())
        sp.bind("<Return>", lambda e: command())

    def _time(self, parent, text: str, var, command) -> None:
        """HH:MM 输入框：失焦 / 回车才校验，边打字边纠正会一直跳字。"""
        row = tk.Frame(parent, bg=theme.CARD)
        row.pack(fill="x", pady=theme.S(2))
        tk.Label(row, text=text, bg=theme.CARD, fg=theme.FG, font=theme.T("body"), anchor="w").pack(
            side="left", fill="x", expand=True)
        entry = ttk.Entry(row, textvariable=var, width=8, justify="center",
                          font=theme.T("body"))
        entry.pack(side="right")
        entry.bind("<FocusOut>", lambda e: command())
        entry.bind("<Return>", lambda e: command())

    # ---------- 应用 ----------
    def refresh(self) -> None:
        s = self.data.settings
        self._loading = True
        self.v_remind.set(bool(s.get("reminders_enabled", True)))
        self.v_end.set(bool(s.get("remind_period_end", True)))
        self.v_24h.set(bool(s.get("show_24h_bar", True)))
        self.v_slot.set(bool(s.get("show_slot_bar", True)))
        self.v_secs.set(int(s.get("reminder_seconds", 5)))
        self.v_font.set(float(s.get("font_scale", 1.0)))
        self.v_course_h.set(int(s.get("course_area_h", 56)))
        self.v_through.set(bool(s.get("click_through", True)))
        self.v_guard.set(int(s.get("topmost_guard_ms", 1000)))
        self.v_auto.set(win32util.is_autostart_enabled())
        self.v_sd_on.set(bool(s.get("shutdown_enabled", False)))
        self.v_sd_time.set(format_hhmm(s.get("shutdown_time", "22:30")))
        self.days.set(s.get("shutdown_days", []))
        self._loading = False
        self.lbl_state.configure(
            text="· 关本窗口不退出；退出：右键托盘图标 →「退出程序」。\n"
                 "· 鼠标穿透开启后，想改设置就右键托盘图标进来。\n"
                 "· 配色 / 透明度：到「外观」页，改完立刻生效。")
        self.lbl_path.configure(text=f"数据文件　{_elide(str(config.config_file()), 62)}")
        self._refresh_shutdown_hint()

    def _apply_remind(self) -> None:
        if self._loading:
            return
        s = self.data.settings
        s["reminders_enabled"] = bool(self.v_remind.get())
        s["remind_period_end"] = bool(self.v_end.get())
        try:
            s["reminder_seconds"] = max(2, min(30, int(self.v_secs.get())))
        except Exception:
            s["reminder_seconds"] = 5
        self.ctl.save_data()

    def _apply_ui(self) -> None:
        if self._loading:
            return
        s = self.data.settings
        s["show_24h_bar"] = bool(self.v_24h.get())
        s["show_slot_bar"] = bool(self.v_slot.get())
        try:
            s["font_scale"] = round(max(0.8, min(1.4, float(self.v_font.get()))), 2)
        except Exception:
            s["font_scale"] = 1.0
        try:
            s["topmost_guard_ms"] = max(500, min(5000, int(self.v_guard.get())))
        except Exception:
            s["topmost_guard_ms"] = 1000
        try:
            s["course_area_h"] = max(28, min(96, int(self.v_course_h.get())))
        except Exception:
            s["course_area_h"] = 56
        s["click_through"] = bool(self.v_through.get())
        self.ctl.save_data()
        self.ctl.topbar.refresh()
        self.ctl.apply_click_through()

    def _apply_autostart(self) -> None:
        if self._loading:
            return
        ok = win32util.set_autostart(bool(self.v_auto.get()))
        self.v_auto.set(win32util.is_autostart_enabled())
        if not ok:
            show_info(self, "设置失败", "写入开机启动项失败，请检查系统权限。")

    def _tip(self, text: str) -> None:
        """状态栏提示挂在 MainWindow 上，tab 自己拿不到，走控制器转一手。"""
        mw = getattr(self.ctl, "main_window", None)
        if mw is not None and hasattr(mw, "toast_tip"):
            try:
                mw.toast_tip(text)
            except Exception:
                pass

    def _apply_shutdown(self) -> None:
        """定时关机：时间非法就退回原值，没选星期就自动关掉开关（避免「开着却不关」）。"""
        if self._loading:
            return
        s = self.data.settings
        raw = self.v_sd_time.get().strip()
        if parse_hhmm(raw) is None:
            self._loading = True
            self.v_sd_time.set(format_hhmm(s.get("shutdown_time", "22:30")))
            self._loading = False
            self._tip("关机时间请用 24 小时制，例如 22:30")
            return
        s["shutdown_time"] = format_hhmm(raw)

        days = self.days.get()
        s["shutdown_days"] = days
        enabled = bool(self.v_sd_on.get())
        if enabled and not days:
            enabled = False
            self._loading = True
            self.v_sd_on.set(False)
            self._loading = False
            self._tip("没有选中任何星期，定时关机已关闭")
        s["shutdown_enabled"] = enabled
        self.ctl.save_data()
        self._refresh_shutdown_hint()

    def _refresh_shutdown_hint(self) -> None:
        s = self.data.settings
        sched = getattr(self.ctl, "shutdown", None)
        state = sched.describe(s) if sched is not None else ""
        notice = int(s.get("shutdown_notice_min", 1) or 1)
        # 只留一行：右栏还有「使用说明」「关于」，多一行就把下面顶出滚动区
        self.lbl_sd.configure(text=f"{state}　·　提前 {notice} 分钟提醒，气泡上可取消")

    def _open_dir(self) -> None:
        try:
            os.startfile(str(config.data_dir()))
        except Exception as exc:
            show_info(self, "打开失败", str(exc))

    def _show_sponsor(self) -> None:
        show_sponsor(self, self.ctl)

    def _recalibrate(self) -> None:
        self.ctl.topbar.recalibrate()
        self.lbl_state.configure(text="已按系统当前时间重新校准，并刷新置顶状态。")

    def _reset(self) -> None:
        if not ask_yes_no(self, "恢复默认", "将清空当前全部作息表、周期安排与课程表并恢复出厂数据，是否继续？"):
            return
        self.ctl.reset_data()
        self.refresh()
