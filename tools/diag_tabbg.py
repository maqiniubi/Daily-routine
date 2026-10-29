"""诊断：作息表页容器自身底色为什么没跟着换。"""
from __future__ import annotations

import os
import sys
import tempfile
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_diag_")

from app import palette, theme, win32util      # noqa: E402
from app.controller import Controller           # noqa: E402
from app.ui import appearance_tab               # noqa: E402
from app.ui.common import init_style            # noqa: E402

win32util.enable_dpi_awareness()
root = tk.Tk()
root.withdraw()
theme.init(root)
init_style(root)
ctl = Controller(root)
ctl.open_settings()
mw = ctl.main_window
mw.tabbar.select(5)
root.update()
tab: appearance_tab.AppearanceTab = mw.tab_appearance

print("当前页签:", mw.tabbar.current())
print("pending:", mw._pending_restyle)

tab._use_preset("light")
root.update()
print("\n[切浅色后]")
print("  theme.BG            =", theme.BG)
print("  light bg            =", palette.PRESETS[1]["ui"]["bg"])
print("  tab_sched bg        =", mw.tab_sched.cget("bg"))
print("  tab_sched path      =", mw.tab_sched)
print("  pending             =", mw._pending_restyle)

# 手动触发补色，看是否生效
mw._flush_pending_restyle(0)
root.update()
print("\n[手动调 _flush_pending_restyle(0) 后]")
print("  tab_sched bg        =", mw.tab_sched.cget("bg"))
print("  pending             =", mw._pending_restyle)

# 再试一次 select(0)
mw.tabbar.select(0)
root.update()
print("\n[select(0) 后]")
print("  tab_sched bg        =", mw.tab_sched.cget("bg"))
print("  theme.BG            =", theme.BG)

root.destroy()
