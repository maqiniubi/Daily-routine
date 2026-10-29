"""验收截图：作息表页「新建 → 选中新表」与新建对话框。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="cb_shot_crud_")

import tkinter as tk

from app import theme, win32util
from app.controller import Controller
from app.ui.common import init_style

SHOTS = Path(__file__).resolve().parent.parent / "shots"
SHOTS.mkdir(exist_ok=True)


def grab(win, name: str) -> None:
    from PIL import ImageGrab

    win.update_idletasks()
    win.lift()
    win.attributes("-topmost", True)
    win.update()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    path = SHOTS / f"crud_{name}.png"
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(str(path))
    print("shot:", path.name, (x, y, w, h), flush=True)


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    ctl.open_settings()
    mw = ctl.main_window
    tab = mw.tab_sched
    root.update()

    # 真正走一遍「新建」：弹窗 → 填名字 → 选模板 → 保存
    tab.add_schedule()
    root.update()

    def walk(w):
        stack = [w]
        while stack:
            cur = stack.pop()
            yield cur
            try:
                stack.extend(cur.winfo_children())
            except tk.TclError:
                continue

    dlg = next((w for w in walk(root) if isinstance(w, tk.Toplevel) and hasattr(w, "_vars")), None)
    if dlg is not None:
        dlg._vars["name"].set("秋季作息")
        if "from" in dlg._vars:
            dlg._vars["from"].set("基础作息")
        root.update()
        grab(dlg, "dialog_new")
        dlg._submit()
    root.update()
    root.after(300, lambda: None)
    mw.update()
    grab(mw, "tab_sched_after_add")
    print("当前选中 =", tab.lbl_title.cget("text"))
    print("左栏 =", [t.strip() for t in tab.listbox.get(0, "end")])
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
