"""复现脚本：换肤两个缺陷的定位工具。

1) 浅色 -> 深色后逐个控件比对，找出「没恢复原色」的元素；
2) 逐段计时 apply_appearance 的各个阶段，定位卡顿热点。

用法：python tools/diag_theme.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = tempfile.mkdtemp(prefix="cb_diag_")
real = Path(os.environ.get("APPDATA", "")) / "ClassBell" / "config.json"
(Path(TMP) / "ClassBell").mkdir(parents=True, exist_ok=True)
if real.exists():
    shutil.copyfile(real, Path(TMP) / "ClassBell" / "config.json")
os.environ["APPDATA"] = TMP

import tkinter as tk                                          # noqa: E402

from app import palette, theme, win32util                     # noqa: E402
from app.controller import Controller                         # noqa: E402
from app.ui.common import init_style                          # noqa: E402


def walk(widget):
    stack = [widget]
    while stack:
        w = stack.pop()
        yield w
        try:
            stack.extend(w.winfo_children())
        except tk.TclError:
            continue


def snapshot(root) -> dict:
    """记录每个控件当前 bg/fg。"""
    out = {}
    for w in walk(root):
        try:
            path = str(w)
        except Exception:
            continue
        for opt in ("bg", "fg"):
            try:
                v = w.cget(opt)
            except Exception:
                continue
            if isinstance(v, str) and v.startswith("#"):
                out[(path, opt)] = v
    return out


def diff(before: dict, after: dict, label: str) -> None:
    """对比两次快照：列出「本该变却没变」的元素。"""
    print(f"\n--- {label} ---")
    stale = []
    for key, old in before.items():
        new = after.get(key)
        if new is None:
            continue
        if old != new:
            continue
        # 值没变：判断它现在是否与当前主题「相容」
        pass
    for key, old in before.items():
        new = after.get(key)
        if new is not None and new == old:
            stale.append((key, old))
    print(f"   颜色未变的控件项：{len(stale)}")
    for key, old in stale[:40]:
        print(f"     {key[0]:<34} {key[1]} = {old}")


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    ctl.open_settings()
    mw = ctl.main_window
    for _ in range(8):
        root.update()
        time.sleep(0.02)

    tab = mw.tab_appearance
    mw.tabbar.select(5)
    for _ in range(8):
        root.update()
        time.sleep(0.02)

    # ---------- 缺陷 1：浅色 -> 深色能否完整还原 ----------
    #
    # 「还原」的严格定义：**与切浅色之前的深色状态逐控件完全一致**。
    # 不能用「这个颜色在不在默认色板里」来判断——深色主题的 FG2/FG3/CARD_HOVER
    # 是 apply_palette 推导出来的，不在 DEFAULT_UI 的锚点值里。
    tab._use_preset("dark")
    for _ in range(8):
        root.update()
        time.sleep(0.02)
    base_snap = snapshot(mw)          # 深色基准

    tab._use_preset("light")
    for _ in range(8):
        root.update()
        time.sleep(0.02)
    light_snap = snapshot(mw)

    tab._use_preset("dark")
    for _ in range(8):
        root.update()
        time.sleep(0.02)
    dark_snap = snapshot(mw)

    # 与深色基准逐项比对：不一致的才算「没还原」
    print(f"深色基准控件项 {len(base_snap)}，浅色快照取值数 {len(set(light_snap.values()))}")
    leftover = []
    for key, old in base_snap.items():
        new = dark_snap.get(key)
        if new is None:
            leftover.append((key, old, "（控件消失）"))
        elif new.lower() != old.lower():
            leftover.append((key, old, new))
    print(f"切回深色后与基准不一致的控件项：{len(leftover)}")
    for key, old, new in leftover[:60]:
        print(f"   {key[0]:<34} {key[1]}：{old} -> {new}")

    # ---------- 缺陷 2：切换耗时 ----------
    print("\n--- 切换耗时 ---")
    for name, key in (("深色->浅色", "light"), ("浅色->深色", "dark"),
                      ("深色->午夜蓝", "midnight"), ("午夜蓝->深色", "dark")):
        t0 = time.perf_counter()
        tab._use_preset(key)
        t1 = time.perf_counter()
        for _ in range(4):
            root.update()
        t2 = time.perf_counter()
        print(f"   {name}: 下发 {1000*(t1-t0):7.1f} ms   重绘 {1000*(t2-t1):6.1f} ms"
              f"   合计 {1000*(t2-t0):7.1f} ms")

    # 分段计时
    print("\n--- apply_appearance 分段 ---")
    from app import palette as pal

    def phase(label, fn):
        t0 = time.perf_counter()
        fn()
        print(f"   {label:<28} {1000*(time.perf_counter()-t0):7.1f} ms")

    s = ctl.data.settings
    phase("palette.apply(重刷 ttk)", lambda: pal.apply(s, root))
    phase("topbar.restyle(就地换色)", lambda: ctl.topbar.restyle())
    phase("topbar.refresh(整条重建)", lambda: ctl.topbar.refresh())
    phase("mw.restyle(整树重着色)", lambda: mw.restyle())

    # 每个页签的控件数与单独换色耗时
    print("\n--- 各页签控件数 / 单独换色耗时 ---")
    from app.ui.main_window import _restyle_tree
    for i, tab in enumerate(mw._tabs()):
        n = len(list(walk(tab)))
        t0 = time.perf_counter()
        _restyle_tree(tab)
        print(f"   页签 {i}: {n:4d} 个控件   换色 {1000*(time.perf_counter()-t0):6.1f} ms")

    t0 = time.perf_counter()
    ctl.apply_appearance()
    print(f"\n   apply_appearance 整体      {1000*(time.perf_counter()-t0):7.1f} ms")
    t0 = time.perf_counter()
    root.update()
    print(f"   随后的重绘 update()        {1000*(time.perf_counter()-t0):7.1f} ms")

    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
