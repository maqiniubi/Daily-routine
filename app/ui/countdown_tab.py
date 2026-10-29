"""倒计时标签页：增删改查目标日期倒计时（融合 CountDay 的核心功能）。"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

from .. import theme
from ..models import Countdown
from .common import FormDialog, ask_yes_no, show_info
from .widgets import Button, RoundedBox


class CountdownTab(tk.Frame):
    @property
    def data(self):
        return self.ctl.data

    def __init__(self, parent, ctl):
        super().__init__(parent, bg=theme.BG)
        self.ctl = ctl

        wrap = tk.Frame(self, bg=theme.BG)
        wrap.pack(fill="both", expand=True)

        head = tk.Frame(wrap, bg=theme.BG)
        head.pack(fill="x", pady=(0, theme.P(2)))
        tk.Label(head, text="倒计时", bg=theme.BG, fg=theme.FG, font=theme.T("headline"),
                 anchor="w").pack(side="left")
        tk.Label(head, text="目标日期按自然日计算", bg=theme.BG, fg=theme.FG3,
                 font=theme.T("caption")).pack(side="left", padx=(theme.S(10), 0), pady=(theme.S(3), 0))

        Button(head, "新增倒计时", self.add, kind="primary").pack(side="right")
        Button(head, "编辑", self.edit, kind="secondary", width=theme.S(56)).pack(
            side="right", padx=(0, theme.S(6)))
        Button(head, "删除", self.remove, kind="ghost", width=theme.S(56)).pack(side="right")

        # 底部统计先占位，避免表格撑满后把它挤出可视区
        foot = tk.Frame(wrap, bg=theme.BG)
        foot.pack(fill="x", side="bottom", pady=(theme.P(2), 0))
        self.lbl_hint = tk.Label(foot, text="", bg=theme.BG, fg=theme.FG3, font=theme.T("caption"),
                                 anchor="w", justify="left", wraplength=theme.S(620))
        self.lbl_hint.pack(side="left")
        Button(foot, "桌面贴纸：显示 / 隐藏", self.toggle_desktop, kind="ghost").pack(side="right")

        box = RoundedBox(wrap, radius=14, fill=theme.CARD, pad=0)
        box.pack(fill="both", expand=True, pady=(theme.S(2), 0))
        inner = tk.Frame(box.body, bg=theme.CARD, padx=theme.P(3), pady=theme.P(2))
        inner.pack(fill="both", expand=True)

        columns = [("name", "名称", 190), ("target", "目标日期", 130), ("left", "剩余", 130),
                   ("bar", "悬浮条", 90), ("desk", "桌面", 90)]
        self.tree = ttk.Treeview(inner, columns=[c[0] for c in columns], show="headings",
                                 selectmode="browse", height=7)
        for key, title, width in columns:
            # 表头与单元格用同一个对齐基准，否则「名称」会飘在左对齐列的中间
            anchor = "w" if key in ("name", "target", "left") else "center"
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=theme.S(width), minwidth=theme.S(60), anchor=anchor,
                             stretch=(key == "name"))
        vs = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview,
                           style="Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y", padx=(theme.S(2), 0))
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<Button-3>", self._row_menu)

        self.lbl_empty = tk.Label(
            inner, text="还没有倒计时\n点右上角「新增倒计时」添加，例如：高考 2027-06-07",
            bg=theme.CARD, fg=theme.FG3, font=theme.T("body"), justify="center")

        self.refresh()

    # ---------------- 数据操作 ----------------
    def selected(self) -> Countdown | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.data.get_countdown(sel[0])

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        today = datetime.now().date()
        # 按目标日期升序排列（未填日期的沉底），和「最近的事最要紧」的直觉一致
        items = sorted(self.data.countdowns,
                       key=lambda c: (c.target_date() is None, c.target_date() or today))
        for cd in items:
            n = cd.days_left(today)
            left = cd.phrase(today)
            self.tree.insert("", "end", iid=cd.id, values=(
                cd.name,
                cd.target or "未设置",
                left,
                "✓" if cd.show_in_bar else "—",
                "✓" if cd.show_desktop else "—",
            ))
            self.tree.item(cd.id, tags=("expired",) if (n is not None and n < 0) else ())
        self.tree.tag_configure("expired", foreground=theme.FG3)

        count = len(self.data.countdowns)
        on_bar = len([c for c in self.data.countdowns if c.show_in_bar])
        on_desk = len([c for c in self.data.countdowns if c.show_desktop])
        self.lbl_hint.configure(
            text=f"共 {count} 个倒计时　·　悬浮条显示 {on_bar} 个　·　桌面贴纸 {on_desk} 个")
        if count:
            self.lbl_empty.place_forget()
        else:
            self.lbl_empty.place(relx=0.5, rely=0.5, anchor="center")

    def _fields(self) -> list[dict]:
        return [
            {"key": "name", "label": "名称", "default": ""},
            {"key": "target", "label": "目标日期", "default": ""},
            {"key": "bar", "label": "悬浮条显示", "kind": "combo", "options": ["是", "否"], "default": "是"},
            {"key": "desk", "label": "桌面贴纸", "kind": "combo", "options": ["是", "否"], "default": "否"},
        ]

    def add(self) -> None:
        default_date = (datetime.now().date() + timedelta(days=30)).strftime("%Y-%m-%d")

        def save(data: dict) -> None:
            cd = Countdown(name=data["name"] or "倒计时", target=data["target"],
                           show_in_bar=data["bar"] == "是", show_desktop=data["desk"] == "是")
            cd.validate()                      # 校验失败由 FormDialog 就地提示
            self.data.countdowns.append(cd)
            self.ctl.save_data()
            self.ctl.after_countdown_change()
            self.refresh()
            self.tree.selection_set(cd.id)

        FormDialog(self.ctl.main_window or self, "新增倒计时", self._fields(),
                   values={"name": "高考", "target": default_date, "bar": "是", "desk": "否"},
                   hint="日期格式：2026-06-07 或 2026-06-07 09:00（只按自然日计算）",
                   on_submit=save)

    def edit(self) -> None:
        cd = self.selected()
        if cd is None:
            show_info(self.ctl.main_window or self, "提示", "请先在列表中选择一个倒计时。")
            return

        def save(data: dict) -> None:
            tmp = Countdown(id=cd.id, name=data["name"] or "倒计时", target=data["target"],
                            show_in_bar=data["bar"] == "是", show_desktop=data["desk"] == "是",
                            pos=list(cd.pos))
            tmp.validate()                     # 先校验再落库，失败时原对象不变
            cd.name, cd.target = tmp.name, tmp.target
            cd.show_in_bar, cd.show_desktop = tmp.show_in_bar, tmp.show_desktop
            self.ctl.save_data()
            self.ctl.after_countdown_change()
            self.refresh()

        FormDialog(self.ctl.main_window or self, "编辑倒计时", self._fields(),
                   values={"name": cd.name, "target": cd.target,
                           "bar": "是" if cd.show_in_bar else "否",
                           "desk": "是" if cd.show_desktop else "否"},
                   hint="日期格式：2026-06-07 或 2026-06-07 09:00", on_submit=save)

    def remove(self) -> None:
        cd = self.selected()
        if cd is None:
            show_info(self.ctl.main_window or self, "提示", "请先在列表中选择一个倒计时。")
            return
        if not ask_yes_no(self.ctl.main_window or self, "删除倒计时",
                          f"确定删除「{cd.name}」吗？此操作不可撤销。"):
            return
        self.data.countdowns = [c for c in self.data.countdowns if c.id != cd.id]
        self.ctl.save_data()
        self.ctl.after_countdown_change()
        self.refresh()

    def _row_menu(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0, bg=theme.CARD_HOVER, fg=theme.FG,
                       activebackground=theme.ACCENT, activeforeground=theme.ON_ACCENT, bd=0,
                       font=theme.T("body"), activeborderwidth=0)
        menu.add_command(label="编辑", command=self.edit)
        menu.add_command(label="切换悬浮条显示", command=self.toggle_bar)
        menu.add_command(label="切换桌面显示", command=self.toggle_desktop_row)
        menu.add_separator()
        menu.add_command(label="删除", command=self.remove)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def toggle_bar(self) -> None:
        cd = self.selected()
        if cd is None:
            return
        cd.show_in_bar = not cd.show_in_bar
        self.ctl.save_data()
        self.ctl.after_countdown_change()
        self.refresh()

    def toggle_desktop_row(self) -> None:
        cd = self.selected()
        if cd is None:
            return
        cd.show_desktop = not cd.show_desktop
        self.ctl.save_data()
        self.ctl.after_countdown_change()
        self.refresh()

    def toggle_desktop(self) -> None:
        """整体开关：桌面贴纸显示 / 隐藏。"""
        on = bool(self.data.settings.get("show_desktop_countdown", False))
        if not on and not [c for c in self.data.countdowns if c.show_desktop]:
            show_info(self.ctl.main_window or self, "还没有桌面倒计时",
                      "请先在列表中右键某个倒计时，选择「切换桌面显示」，"
                      "或在编辑窗口把「桌面贴纸」设为「是」。")
            return
        self.data.settings["show_desktop_countdown"] = not on
        self.ctl.save_data()
        self.ctl.sync_desktop_countdown()
        self.refresh()
