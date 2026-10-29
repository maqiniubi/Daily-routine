"""外观自定义（v1.6.0）测试：数据层 + 真实窗口联动。

两部分：
1. 无界面：palette 清洗 / 预设匹配 / 透明度夹取 / theme 令牌推导 / models 落盘清洗；
2. 有界面：真实 Controller + 设置中心 + 外观页，验证「选预设 → 存盘 → theme 生效
   → 控件回填 → 悬浮条重建」整条链路，以及手填 hex、改透明度、恢复默认。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_appearance_")

from app import palette, theme, win32util                          # noqa: E402
from app.controller import Controller                              # noqa: E402
from app.models import AppData, default_settings                   # noqa: E402
from app.ui import appearance_tab                                  # noqa: E402
from app.ui.common import init_style                               # noqa: E402

PASS = 0
FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    global PASS
    if not cond:
        FAILED.append(label)
        print(f"  FAIL {label}")
    else:
        PASS += 1
        print(f"  ok  {label}")


# ---------------------------------------------------------------- 数据层
def test_normalize() -> None:
    check(palette.normalize("#0A84FF") == "#0a84ff", "大写 hex 归一化")
    check(palette.normalize("0a84ff") == "#0a84ff", "缺 # 自动补")
    check(palette.normalize("#abc") == "#aabbcc", "三位 hex 展开")
    check(palette.normalize("  #0A84FF  ") == "#0a84ff", "去空格")
    check(palette.normalize("#xyzxyz") is None, "非法字符拒绝")
    check(palette.normalize("#12345") is None, "五位拒绝")
    check(palette.normalize(123) is None, "非字符串拒绝")
    check(palette.normalize("") is None, "空串拒绝")


def test_normalize_theme() -> None:
    t = palette.normalize_theme({"bg": "#111111", "bad": "x", "fg": 5})
    check(t["bg"] == "#111111" and t["fg"] == palette.DEFAULT_UI["fg"],
          "合法值保留、非法值回落到默认")
    check(set(t) == set(palette.UI_SLOTS), "槽位完整")
    check(palette.normalize_theme(None) == palette.DEFAULT_UI, "整块缺失回落")
    bar = palette.normalize_theme({"accent": "#30d158"}, palette.BAR_SLOTS, palette.DEFAULT_BAR)
    check(bar["accent"] == "#30d158" and set(bar) == set(palette.BAR_SLOTS), "悬浮条槽位独立")


def test_presets() -> None:
    keys = [p["key"] for p in palette.PRESETS]
    check(len(keys) == len(set(keys)), "预设键不重复")
    for p in palette.PRESETS:
        check(set(p["ui"]) == set(palette.UI_SLOTS) and
              set(p["bar"]) == set(palette.BAR_SLOTS), f"预设 {p['key']} 槽位完整")
    check(palette.match_preset(palette.PRESETS[1]["ui"], palette.PRESETS[1]["bar"])["key"]
          == "light", "浅色预设可被匹配")
    custom = dict(palette.DEFAULT_UI, accent="#123456")
    check(palette.match_preset(custom, palette.DEFAULT_BAR) is None, "自定义色不匹配任何预设")
    check(palette.preset("nope") is None, "未知预设键返回 None")


def test_alphas() -> None:
    check(palette.alphas({}) == (palette.DEFAULT_UI_ALPHA, palette.DEFAULT_BAR_ALPHA),
          "空设置取默认不透明度")
    check(palette.alphas({"ui_alpha": 0.5, "bar_alpha": 1.5}) == (0.75, 1.0),
          "超出区间被夹住")
    check(palette.alphas({"ui_alpha": "x", "bar_alpha": None}) ==
          (palette.DEFAULT_UI_ALPHA, palette.DEFAULT_BAR_ALPHA), "非法值回落默认")


def test_apply_palette() -> None:
    try:
        ui, bar = palette.apply({"ui_theme": palette.PRESETS[1]["ui"],
                                 "bar_theme": palette.PRESETS[1]["bar"]},
                                root=None)
        check(theme.BG == "#eceef2" and theme.CARD == "#ffffff", "浅色令牌写入 theme")
        check(theme.is_dark(theme.BG) is False, "浅色下 is_dark 为假")
        check(theme.lum(theme.SURFACE) < theme.lum(theme.BG), "浅色 SURFACE 比背景暗（有层次）")
        check(theme.ON_ACCENT == "#ffffff", "亮强调色配深字")
        check(theme.lum(theme.BAR_TRACK) < theme.lum(theme.GLASS), "浅色条轨道略暗于底色（凹槽）")

        palette.apply({"ui_theme": palette.PRESETS[3]["ui"],      # 松林绿
                       "bar_theme": palette.PRESETS[3]["bar"]})
        check(theme.BG == "#0b1310" and theme.is_dark(theme.BG) is True, "深色令牌生效")
        check(theme.lum(theme.SURFACE) > theme.lum(theme.BG), "深色 SURFACE 比背景亮")
        check(theme.lum(theme.BAR_TRACK) < theme.lum(theme.GLASS), "深色条轨道压暗")
        check(theme.lum(theme.FG2) < theme.lum(theme.FG), "FG2 比 FG 弱")
        check(theme.ACCENT_DIM != theme.ACCENT, "ACCENT_DIM 派生")
        for name in ("BG", "CARD", "FG", "FG2", "FG3", "LINE", "SURFACE", "CARD_HOVER",
                     "FILL", "TRACK", "PILL", "SCROLL", "ACCENT", "ON_ACCENT",
                     "GLASS", "GLASS_DEEP", "BAR_BG", "BAR_FG", "BAR_FG2", "BAR_FG3",
                     "BAR_LINE", "BAR_ACCENT", "BAR_TRACK", "BAR_TICK", "BAR_TICK_WEAK",
                     "BAR_EDGE"):
            check(str(getattr(theme, name)).startswith("#"), f"令牌 {name} 是合法色值")

        # 换色映射：按「角色」把旧色翻译成新色
        palette.apply({"ui_theme": palette.PRESETS[1]["ui"], "bar_theme": palette.PRESETS[1]["bar"]})
        check(theme.remap("#eceef2", "bg") == "#eceef2", "当前配色的底色保持不变")
        palette.apply({"ui_theme": palette.PRESETS[3]["ui"], "bar_theme": palette.PRESETS[3]["bar"]})
        check(theme.remap("#eceef2", "bg") == palette.PRESETS[3]["ui"]["bg"],
              "旧底色按角色映到新底色")
        check(theme.remap("#123456", "bg") == "#123456",
              "字面量颜色（不在任何配色里）保持不变")
    finally:
        palette.apply({"ui_theme": palette.DEFAULT_UI, "bar_theme": palette.DEFAULT_BAR})


def test_remap_roles() -> None:
    """角色映射：白色卡片能还原、白色文字不串味、多次切换仍可还原。"""
    try:
        palette.apply({"ui_theme": palette.DEFAULT_UI, "bar_theme": palette.DEFAULT_BAR})
        palette.apply({"ui_theme": palette.PRESETS[1]["ui"], "bar_theme": palette.PRESETS[1]["bar"]})
        # 浅色主题：卡片底色是纯白，按钮上的白字也是纯白（ON_ACCENT）
        check(palette.PRESETS[1]["ui"]["card"] == "#ffffff", "浅色主题卡片是纯白")
        check(theme.remap("#ffffff", "bg") == "#ffffff", "浅色下白卡片映射到白卡片")
        palette.apply({"ui_theme": palette.DEFAULT_UI, "bar_theme": palette.DEFAULT_BAR})
        check(theme.remap("#ffffff", "bg") == palette.DEFAULT_UI["card"],
              "切回深色：白卡片还原成深色卡片（缺陷 1 的核心断言）")
        check(theme.remap("#1c1c1e", "fg") == palette.DEFAULT_UI["fg"],
              "浅色主题的深色文字还原成深色主题的主文字色")
        # 文字位不能被当成底色位
        check(theme.remap("#ffffff", "fg") != palette.DEFAULT_UI["card"],
              "白字不会被误当成卡片底色")
        # 连续切换多轮仍能还原
        for key in ("midnight", "light", "forest", "light"):
            palette.apply({"ui_theme": palette.PRESETS[[p["key"] for p in palette.PRESETS].index(key)]["ui"],
                           "bar_theme": palette.PRESETS[[p["key"] for p in palette.PRESETS].index(key)]["bar"]})
        palette.apply({"ui_theme": palette.DEFAULT_UI, "bar_theme": palette.DEFAULT_BAR})
        check(theme.remap("#ffffff", "bg") == palette.DEFAULT_UI["card"],
              "连续切换多次后仍能还原成深色卡片")
        check(theme.remap("#0b0b0d", "bg") == palette.DEFAULT_UI["bg"], "深色底色保持稳定")
    finally:
        palette.apply({"ui_theme": palette.DEFAULT_UI, "bar_theme": palette.DEFAULT_BAR})


def test_restore_defaults() -> None:
    s = default_settings()
    s["ui_theme"] = dict(palette.DEFAULT_UI, bg="#123456")
    s["bar_alpha"] = 0.6
    palette.restore_defaults(s)
    check(s["ui_theme"] == palette.DEFAULT_UI and s["bar_alpha"] == palette.DEFAULT_BAR_ALPHA,
          "恢复默认只改外观字段")


def test_models_sanitize() -> None:
    raw = {
        "version": 1,
        "settings": {
            "ui_theme": {"bg": "#zzzzzz", "card": "#ffffff"},
            "bar_theme": "垃圾",
            "ui_alpha": 0.1,
            "bar_alpha": 9,
        },
        "schedules": [{"name": "x", "start": "08:00", "end": "08:40"}],
        "week": {},
    }
    data = AppData(raw)
    s = data.settings
    check(s["ui_theme"]["bg"] == palette.DEFAULT_UI["bg"], "非法背景色被清洗")
    check(s["ui_theme"]["card"] == "#ffffff", "合法卡片色保留")
    check(s["bar_theme"] == palette.DEFAULT_BAR, "整块非法悬浮条配色回落")
    check(s["ui_alpha"] == 0.75 and s["bar_alpha"] == 1.0, "透明度夹到合法区间")


# ---------------------------------------------------------------- 界面联动
def _walk(widget):
    stack = [widget]
    while stack:
        w = stack.pop()
        yield w
        try:
            stack.extend(w.winfo_children())
        except tk.TclError:
            continue


def _colors_of(widget) -> list[tuple[str, str, str]]:
    """收集控件树上所有以 # 开头的 bg / fg。"""
    out = []
    for w in _walk(widget):
        for opt in ("bg", "fg"):
            try:
                val = w.cget(opt)
            except Exception:
                continue
            if isinstance(val, str) and val.startswith("#"):
                out.append((str(w), opt, val))
    return out


def test_switch_restores_everything() -> None:
    """缺陷 1 回归：浅色 -> 深色后，不能有任何控件残留浅色取值。"""
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    try:
        ctl.open_settings()
        mw = ctl.main_window
        mw.tabbar.select(5)
        root.update()
        tab: appearance_tab.AppearanceTab = mw.tab_appearance

        # 「还原」的严格定义：与切浅色之前的深色状态**逐控件完全一致**。
        # 不能用「颜色在不在默认色板里」判断——深色主题的 FG2/FG3/CARD_HOVER
        # 是 apply_palette 推导出来的，不在 DEFAULT_UI 的锚点值里。
        base = {(path, opt): val for path, opt, val in _colors_of(mw)}

        light = palette.PRESETS[1]
        tab._use_preset("light")
        root.update()
        check(theme.BG == light["ui"]["bg"], "已切到浅色")

        tab._use_preset("dark")
        root.update()
        check(theme.BG == palette.DEFAULT_UI["bg"], "已切回深色")

        cur = {(path, opt): val for path, opt, val in _colors_of(mw)}
        mismatched = [(k, base[k], cur.get(k)) for k in base
                      if cur.get(k, "").lower() != base[k].lower()]
        check(not mismatched,
              f"切回深色后与切换前的深色状态逐控件一致（基准 {len(base)} 项，"
              f"不一致 {len(mismatched)} 项）")
        for k, old, new in mismatched[:8]:
            print(f"       不一致 {k[0]} {k[1]}：{old} -> {new}")

        # 浅色主题里的取值，深色主题里没有的，才算「残留」
        light_values = {v.lower() for v in light["ui"].values()} | \
                       {v.lower() for v in light["bar"].values()}
        dark_values = {v.lower() for v in palette.DEFAULT_UI.values()} | \
                      {v.lower() for v in palette.DEFAULT_BAR.values()}
        # 强调色上的白字（ON_ACCENT）两种主题下都是白，不算残留
        allowed = {theme.ON_ACCENT.lower()}
        stale = [(path, opt, val) for path, opt, val in _colors_of(mw)
                 if val.lower() in light_values and val.lower() not in dark_values
                 and val.lower() not in allowed]
        check(not stale, f"切回深色后没有控件残留浅色取值（发现 {len(stale)} 处）")
        for path, opt, val in stale[:8]:
            print(f"       残留 {path} {opt} = {val}")

        # 白色卡片必须变回深色卡片
        white_left = [(path, opt) for path, opt, val in _colors_of(mw)
                      if val.lower() == "#ffffff" and opt == "bg"]
        check(not white_left, f"没有白色底色残留（发现 {len(white_left)} 处）")

        # 连续切几轮，结果必须稳定
        for key in ("light", "midnight", "light", "dark"):
            tab._use_preset(key)
            root.update()
        stale2 = [(path, opt, val) for path, opt, val in _colors_of(mw)
                  if val.lower() in light_values and val.lower() not in dark_values
                  and val.lower() not in allowed]
        check(not stale2, f"连续切换多轮后仍无残留（发现 {len(stale2)} 处）")

        # 看不见的页签切过去时必须补上换色（否则会看到旧配色）
        tab._use_preset("light")
        root.update()
        mw.tabbar.select(0)
        root.update()
        sched = mw.tab_sched
        sched_colors = [v.lower() for _p, _o, v in _colors_of(sched)]
        check(theme.CARD.lower() in sched_colors,
              f"切到作息表页时补上了换色（卡片色 {theme.CARD}）")
        leftover_sched = [(pa, op, v) for pa, op, v in _colors_of(sched)
                          if v.lower() == palette.DEFAULT_UI["bg"].lower()]
        check(not leftover_sched,
              f"作息表页没有残留深色底色（发现 {len(leftover_sched)} 处）")
        for pa, op, v in leftover_sched[:8]:
            print(f"       残留 {pa} {op} = {v}")

        # 页签容器**自身**的底色也要跟着换：它不在子控件的遍历范围里，
        # 以前只换子控件，于是容器一直停在上一轮配色（深色底留在浅色界面上）。
        check(sched.cget("bg").lower() == theme.BG.lower(),
              f"页签容器自身底色已换成当前配色（{theme.BG}）")

        # 切走再切回来，容器底色还得是对的
        mw.tabbar.select(5)
        root.update()
        mw.tabbar.select(0)
        root.update()
        check(sched.cget("bg").lower() == theme.BG.lower(),
              "切走再切回后页签容器底色仍正确")
        for pa, op, v in leftover_sched[:6]:
            print(f"       残留 {pa} {op} = {v}")
        mw.tabbar.select(5)
        root.update()
    finally:
        try:
            ctl.shutdown()
        except Exception:
            pass
        root.destroy()


def test_switch_is_smooth() -> None:
    """缺陷 2 回归：换配色不该卡。设一个宽松但明确的耗时上限。"""
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    try:
        ctl.open_settings()
        mw = ctl.main_window
        mw.tabbar.select(5)
        root.update()
        tab: appearance_tab.AppearanceTab = mw.tab_appearance

        samples = []
        for key in ("light", "dark", "midnight", "dark"):
            t0 = time.perf_counter()
            tab._use_preset(key)
            root.update()
            samples.append((time.perf_counter() - t0) * 1000)
        worst = max(samples)
        print(f"       各次切换耗时：{['%.0f' % s for s in samples]} ms")
        check(worst < 400, f"最慢一次切换 {worst:.0f} ms < 400 ms 上限")

        # 悬浮条换色走的是就地换色，不能再整条重建
        t0 = time.perf_counter()
        ctl.topbar.restyle()
        root.update()
        bar_ms = (time.perf_counter() - t0) * 1000
        print(f"       悬浮条就地换色：{bar_ms:.0f} ms")
        check(bar_ms < 120, f"悬浮条就地换色 {bar_ms:.0f} ms < 120 ms 上限")
    finally:
        try:
            ctl.shutdown()
        except Exception:
            pass
        root.destroy()


def _topbar_paint(topbar) -> list:
    """采集悬浮条的「实际着色」：画布图元的颜色 + 标签的底色/字色。

    不能用屏幕截图比对——悬浮条是 layered 窗口，截图会把下层窗口的残影
    一起拍进来（合成伪影），比出来的差异不是配色问题。
    """
    out = []
    for name in ("cv_gloss", "cv_day", "cv_slots", "cv_edge"):
        cv = getattr(topbar, name, None)
        if cv is None:
            continue
        for item in cv.find_all():
            for opt in ("fill", "outline"):
                try:
                    val = cv.itemcget(item, opt)
                except tk.TclError:
                    continue
                if isinstance(val, str) and val.startswith("#"):
                    # 不记图元 ID：重绘会重建图元，ID 会递增，颜色才是要比的
                    out.append((name, opt, val.lower()))
    for name in ("lbl_date", "lbl_plan", "lbl_cd", "lbl_state", "lbl_sub", "lbl_clock"):
        lbl = getattr(topbar, name, None)
        if lbl is None:
            continue
        for opt in ("bg", "fg"):
            try:
                val = lbl.cget(opt)
            except tk.TclError:
                continue
            out.append((name, opt, val.lower()))
    for part in (topbar._bar_badge, topbar._bar_button):
        if part is None:
            continue
        for attr in ("_bg", "_base", "_fg", "_fg2", "_parent_bg"):
            val = getattr(part, attr, None)
            if isinstance(val, str):
                out.append((type(part).__name__, attr, val.lower()))
    return out


def test_topbar_restores_colors() -> None:
    """悬浮条浅色 -> 深色后，每个图元的颜色都要和切换前完全一致。"""
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    try:
        ctl.open_settings()
        for _ in range(10):
            root.update()
        topbar = ctl.topbar

        tab = ctl.main_window.tab_appearance
        ctl.main_window.tabbar.select(5)
        root.update()
        tab._use_preset("dark")
        root.update()
        before = _topbar_paint(topbar)
        check(len(before) > 20, f"采集到悬浮条着色样本 {len(before)} 条")

        tab._use_preset("light")
        root.update()
        light = _topbar_paint(topbar)
        check(any("#" in item[-1] and item[-1] != before[0][-1] for item in light),
              "切到浅色后悬浮条颜色确实变了")

        tab._use_preset("dark")
        root.update()
        after = _topbar_paint(topbar)
        check(len(after) == len(before), "往返后图元数量一致")
        diff = [(b, a) for b, a in zip(before, after) if b != a]
        check(not diff, f"悬浮条配色完整还原（不一致 {len(diff)} 处）")
        for b, a in diff[:6]:
            print(f"       {b} -> {a}")
    finally:
        try:
            ctl.shutdown()
        except Exception:
            pass
        root.destroy()


def test_ui_flow() -> None:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    try:
        ctl.open_settings()
        mw = ctl.main_window
        mw.tabbar.select(5)
        tab: appearance_tab.AppearanceTab = mw.tab_appearance
        root.update()
        check(tab.winfo_exists(), "外观页已挂载")

        # ---- 选预设 ----
        tab._use_preset("midnight")
        root.update()
        s = ctl.data.settings
        check(s["ui_theme"]["bg"] == "#0a1020", "预设写进 settings")
        check(theme.BG == "#0a1020", "预设下发到 theme")
        check(tab._ui_rows["bg"]._var.get() == "#0a1020", "色值行回填预设色")
        check(tab.v_ui_alpha.get() == 1.0, "界面透明度回填")

        # ---- 存盘 ----
        ctl.save_data()
        disk = json.loads((Path(os.environ["APPDATA"]) / "ClassBell" / "config.json")
                          .read_text(encoding="utf-8"))
        check(disk["settings"]["ui_theme"]["bg"] == "#0a1020", "配色已持久化到磁盘")
        check(AppData(disk).settings["bar_theme"] == dict(palette.PRESETS[2]["bar"]),
              "重读配置后悬浮条配色无损")

        # ---- 手填 hex ----
        row = tab._ui_rows["accent"]
        row._var.set("#ff9f0a")
        row._commit()
        root.update()
        check(ctl.data.settings["ui_theme"]["accent"] == "#ff9f0a", "手填 hex 生效")
        check(row._var.get() == "#ff9f0a", "色值框保持新值")
        row._var.set("not-a-color")
        row._commit()
        check(row._var.get() == "#ff9f0a", "非法输入退回原值")
        check(ctl.data.settings["ui_theme"]["accent"] == "#ff9f0a", "非法输入不写盘")

        # ---- 改透明度 ----
        tab.v_bar_alpha.set(0.6)
        tab._set_alpha("bar")
        root.update()
        check(ctl.data.settings["bar_alpha"] == 0.6, "悬浮条透明度写盘")
        tab.v_ui_alpha.set(0.1)
        tab._set_alpha("ui")
        check(ctl.data.settings["ui_alpha"] == 0.75, "透明度低于下限被夹")

        # ---- 悬浮条整条重建不炸 ----
        ctl.apply_appearance()
        root.update()
        check(ctl.topbar.root.winfo_exists(), "apply_appearance 后悬浮条仍存活")

        # ---- 恢复默认 ----
        appearance_tab.ask_yes_no = lambda *a, **k: True
        tab._reset()
        root.update()
        check(ctl.data.settings["ui_theme"] == palette.DEFAULT_UI, "恢复默认生效")
        check(theme.BG == palette.DEFAULT_UI["bg"], "恢复默认后 theme 回落")
        check(tab._ui_rows["bg"]._var.get() == palette.DEFAULT_UI["bg"], "控件同步默认色")

        # ---- 作息数据不受影响 ----
        check(len(ctl.data.schedules) > 0, "恢复外观不动作息表数据")
    finally:
        try:
            ctl.shutdown()
        except Exception:
            pass
        root.destroy()


def main() -> None:
    test_normalize()
    test_normalize_theme()
    test_presets()
    test_alphas()
    test_apply_palette()
    test_restore_defaults()
    test_models_sanitize()
    test_remap_roles()
    test_ui_flow()
    test_switch_restores_everything()
    test_topbar_restores_colors()
    test_switch_is_smooth()
    if FAILED:
        print(f"\n{len(FAILED)} FAILED")
        sys.exit(1)
    print(f"\nALL PASSED ({PASS} checks)")


if __name__ == "__main__":
    main()
