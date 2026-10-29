"""作息表增删改的回归测试：新建 / 复制 / 改名 / 删除后，左栏列表、右侧表格、
数据文件三者必须同步；删除后点击残留行不得抛异常。

复用 test_ui 的做法：临时 APPDATA、真实驱动对话框（自动点「保存」/「确定」）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_crud_")

from app import theme, win32util                                    # noqa: E402
from app.controller import Controller                               # noqa: E402
from app.ui.common import init_style                                # noqa: E402

FAILED: list[str] = []
ERRORS: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        FAILED.append(label)


def walk(widget):
    stack = [widget]
    while stack:
        w = stack.pop()
        yield w
        try:
            stack.extend(w.winfo_children())
        except tk.TclError:
            continue


def form_dialogs(root) -> list[tk.Toplevel]:
    out = []
    for w in walk(root):
        if isinstance(w, tk.Toplevel) and hasattr(w, "_vars"):
            try:
                if w.winfo_exists() and w.state() != "withdrawn":
                    out.append(w)
            except tk.TclError:
                continue
    return out


def message_boxes(root) -> list[tk.Toplevel]:
    out = []
    for w in walk(root):
        if isinstance(w, tk.Toplevel) and hasattr(w, "result") and not isinstance(w, tk.Frame):
            try:
                if w.winfo_exists():
                    out.append(w)
            except tk.TclError:
                continue
    return out


def click_text(root, texts: tuple[str, ...]) -> bool:
    """在已弹出的对话框里按文字找自绘按钮并点下去。"""
    for box in message_boxes(root):
        for w in walk(box):
            if getattr(w, "_text", None) in texts and hasattr(w, "_command"):
                try:
                    w._command()
                except tk.TclError:
                    return False
                return True
    return False


def auto_confirm(root, rounds: int = 6) -> None:
    """确认框是模态的（wait_window），必须靠 after 在嵌套循环里点掉。"""
    def poke(n: int) -> None:
        if click_text(root, ("确定", "知道了")) and n > 0:
            root.after(60, lambda: poke(n - 1))

    root.after(120, lambda: poke(rounds))


def submit_forms(root, values: dict, limit: int = 4) -> int:
    """把当前挂着的表单逐个提交（兼容「新建 → 选模板」两级弹窗）。"""
    done = 0
    for _ in range(limit):
        pending = form_dialogs(root)
        if not pending:
            break
        dlg = pending[-1]
        for key, val in values.items():
            if key in dlg._vars:
                dlg._vars[key].set(val)
        dlg._submit()
        root.update()
        done += 1
    return done


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()

    def report(exc_type, exc_value, exc_tb):
        ERRORS.append("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    root.report_callback_exception = report
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    ctl.open_settings()
    mw = ctl.main_window
    tab = mw.tab_sched
    root.update()

    def listbox_items() -> tuple:
        return tuple(t.strip() for t in tab.listbox.get(0, "end"))

    def selected_index() -> int:
        sel = tab.listbox.curselection()
        return -1 if not sel else int(sel[0])

    # ---------------- 1. 新建（带模板） ----------------
    print("[1] 新建作息表")
    before = len(ctl.data.schedules)
    tab.add_schedule()
    root.update()
    check(len(form_dialogs(root)) >= 1, "点「新建」后弹出表单")
    submit_forms(root, {"name": "回归测试作息", "from": "基础作息"})
    root.update()

    sched = ctl.data.get_schedule(tab._current_id)
    check(len(ctl.data.schedules) == before + 1, f"数据里多出一张表（{before} -> {len(ctl.data.schedules)}）")
    check(sched is not None and sched.name == "回归测试作息", "当前选中 = 新建的作息表")
    check("回归测试作息" in listbox_items(), f"左栏列表出现新表 = {listbox_items()}")
    check(selected_index() == [s.name for s in ctl.data.schedules].index("回归测试作息"),
          f"左栏选中行指向新表（第 {selected_index()} 行）")
    check(tab.lbl_title.cget("text") == "回归测试作息", "右侧标题同步")
    expect_rows = len(sched.periods) if sched else -1
    check(len(tab.tree.get_children()) == expect_rows,
          f"右侧表格行数 = {len(tab.tree.get_children())}（期望 {expect_rows}）")
    check(expect_rows > 0, "模板时段已一起复制过来（不会出现空表）")

    # ---------------- 2. 新建空白表 ----------------
    print("[2] 新建空白作息表")
    tab.add_schedule()
    root.update()
    submit_forms(root, {"name": "空白作息", "from": "空白"})
    root.update()
    blank = ctl.data.get_schedule(tab._current_id)
    check(blank is not None and blank.name == "空白作息", "空白表已创建并选中")
    check("空白作息" in listbox_items(), "左栏列表出现空白表")
    check(len(tab.tree.get_children()) == 0, "空白表表格为空（符合预期）")
    check("添加时段" in tab.lbl_meta.cget("text"), f"空表给出引导文案 = {tab.lbl_meta.cget('text')}")

    # ---------------- 3. 复制 / 改名 ----------------
    print("[3] 复制与改名")
    tab.duplicate_schedule()
    root.update()
    names = ctl.data.schedule_names()
    check(len(names) == len(set(names)), f"复制后名称仍然唯一 = {names}")
    check(names[-1] in listbox_items(), f"左栏出现副本 = {names[-1]}")

    target = ctl.data.schedules[-1]
    tab._current_id = target.id
    tab.refresh()
    check(tab._current_id == target.id, "手工选中副本后 refresh 不丢选中态")
    tab.rename_schedule()
    root.update()
    submit_forms(root, {"name": "改名后的表"})
    root.update()
    check("改名后的表" in listbox_items(), f"左栏同步改名 = {listbox_items()}")
    check(tab.lbl_title.cget("text") == "改名后的表", "右侧标题同步改名")

    # ---------------- 4. 删除 ----------------
    print("[4] 删除作息表")
    victim = ctl.data.schedules[-1]
    tab._current_id = victim.id
    tab.refresh()
    auto_confirm(root)
    tab.delete_schedule()
    root.update()
    check(ctl.data.get_schedule(victim.id) is None, "数据已删除该作息表")
    check(victim.name not in listbox_items(), f"左栏不再残留被删项 = {listbox_items()}")
    check(len(listbox_items()) == len(ctl.data.schedules),
          f"列表行数与数据一致（{len(listbox_items())} / {len(ctl.data.schedules)}）")
    check(ctl.data.get_schedule(tab._current_id) is not None, "删除后当前选中自动改到有效作息表")
    check(selected_index() >= 0 and ctl.data.schedules[selected_index()].id == tab._current_id,
          "左栏高亮行与当前选中一致")

    # 逐行点击：删除后不允许再出现 IndexError
    for i in range(len(listbox_items())):
        tab.listbox.selection_clear(0, "end")
        tab.listbox.selection_set(i)
        tab._on_pick()
    root.update()
    check(not ERRORS, "逐行点击没有再抛出异常")

    # ---------------- 5. 时段增删 ----------------
    print("[5] 时段增删")
    tab._current_id = ctl.data.schedules[0].id
    tab.refresh()
    sched = tab.current_schedule()
    rows_before = len(tab.tree.get_children())
    tab.add_period()
    root.update()
    submit_forms(root, {"name": "回归时段", "start": "21:00", "end": "21:45"})
    root.update()
    check(len(tab.tree.get_children()) == rows_before + 1,
          f"新增时段后表格 +1（{rows_before} -> {len(tab.tree.get_children())}）")

    pid = sched.sorted_periods()[-1].id
    tab.tree.selection_set(pid)
    auto_confirm(root)
    tab.delete_period()
    root.update()
    check(len(tab.tree.get_children()) == rows_before,
          f"删除时段后表格恢复（{len(tab.tree.get_children())}）")
    check(len(tab.current_schedule().periods) == rows_before, "数据与表格一致")

    # 课程表页应当跟着更新
    mw.tab_course.refresh()
    root.update()
    check(len(mw.tab_course.tree.get_children()) == rows_before,
          "课程表页行数同步")

    root.update()
    print("\n回调异常：", "无" if not ERRORS else "")
    for e in ERRORS:
        print(e)
    print("FAILED:", FAILED if FAILED else "none")
    root.destroy()
    return 1 if (FAILED or ERRORS) else 0


if __name__ == "__main__":
    sys.exit(main())
