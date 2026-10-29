"""界面交互测试（无人工干预）：周切换、课程录入、气泡自动消失、悬浮条高度。"""
from __future__ import annotations

import sys
import tkinter as tk
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 测试进程一律用临时数据目录：绝不能读写用户真实的 %APPDATA%\ClassBell
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_test_")


from app import theme, win32util
from app.controller import Controller
from app.ui.common import init_style

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        FAILED.append(label)


def main() -> int:
    win32util.enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    theme.init(root)
    init_style(root)
    ctl = Controller(root)
    out: dict = {}

    def step1() -> None:
        check(ctl.topbar.height() > 20, f"悬浮条高度自适应 = {ctl.topbar.height()}px")
        # 状态栏有 5 种文案形态，别只认前几种：
        # 「正在上课 · X」「距 X 还有 …」「<时段名>中」「今日作息已结束」「今日暂无安排」。
        # 漏掉「…中」这一类会让测试只在特定时刻通过（比如正落在午休/大课间里）。
        state_text = ctl.topbar.lbl_state.cget("text")
        check(bool(state_text) and (
            state_text.startswith("正在") or state_text.startswith("距")
            or state_text.endswith("中") or "已结束" in state_text
            or "暂无" in state_text),
            f"状态栏文案 = {state_text}")
        ctl.open_settings()

    def step_bar_area() -> None:
        """课程名称显示区高度 + 鼠标穿透。"""
        base = ctl.topbar.height()
        check(base > 100, f"悬浮条高度 = {base}px")
        hwnd = ctl.topbar._hwnd
        check(win32util.is_click_through(hwnd), "悬浮条默认开启鼠标穿透")

        ctl.data.settings["course_area_h"] = 96
        ctl.topbar.refresh()
        root.update()
        tall = ctl.topbar.height()
        check(tall > base + 10, f"调高课程名称区域后条变高（{base} -> {tall}）")

        ctl.data.settings["course_area_h"] = 28
        ctl.topbar.refresh()
        root.update()
        short = ctl.topbar.height()
        check(short < base, f"调低后条变矮（{short}）")

        ctl.data.settings["course_area_h"] = 56          # 还原默认，别影响后面的用例
        ctl.topbar.refresh()
        root.update()

        ctl.data.settings["click_through"] = False
        ctl.apply_click_through()
        root.update()
        check(not win32util.is_click_through(hwnd), "关闭穿透后 exstyle 已清除")
        ctl.data.settings["click_through"] = True
        ctl.apply_click_through()
        root.update()
        check(win32util.is_click_through(hwnd), "重新开启穿透即生效")

        mw = ctl.main_window
        check(mw is None or not win32util.is_click_through(win32util.hwnd_of(mw)),
              "设置中心本身不穿透")

    def step2() -> None:
        w = ctl.main_window
        check(w is not None and w.winfo_exists(), "设置中心已打开")
        w.nb.select(1)
        root.update_idletasks()          # 切页后要等一次布局，winfo_width 才有值
        tab = w.tab_week
        picker = tab.rows.grid_slaves(row=0, column=1)[0]
        check(picker.winfo_width() > 10 and isinstance(picker, tk.Frame), "每日选择器已渲染")
        names = ctl.data.schedule_names()
        check(tab._vars["mon"].get() in names, f"周一当前值 = {tab._vars['mon'].get()}")

        old = ctl.data.week["mon"]
        tab._vars["mon"].set("周三半天（示例）")
        tab._apply("mon")
        root.update()
        check(ctl.data.week["mon"] != old, "切换周一的作息表已生效")
        check(tab._sum_mon.cget("text").startswith("周三半天"), "摘要同步更新")

        tab._vars["mon"].set(ctl.data.schedules[0].name)
        tab._apply("mon")
        root.update()
        check(ctl.data.week["mon"] == old, "还原成功")

    def step3() -> None:
        w = ctl.main_window
        w.nb.select(2)
        tab = w.tab_course
        key = tab.day_key()
        sched = ctl.data.schedule_for_day(key)
        pid = sched.sorted_periods()[1].id
        ctl.data.courses_for_day(key)[pid] = "数学"
        tab.refresh()
        row = tab.tree.item(pid, "values")
        check(row and row[-1] == "数学", f"课程表显示课程 = {row}")
        out["tree_rows"] = len(tab.tree.get_children())
        check(out["tree_rows"] == len(sched.periods), "课程表行数与该日时段数一致")

    def step_scroll() -> None:
        w = ctl.main_window
        w.geometry(f"{theme.S(700)}x{theme.S(360)}")
        w.update_idletasks()
        w.nb.select(1)
        w.update_idletasks()
        tab = w.tab_week
        tab.reveal_today(False)
        root.update()
        check(tab.scroll._bar_shown, "内容超高时出现滚动条")
        tab.scroll.scroll_to_bottom()
        root.update()
        check(round(tab.scroll.canvas.yview()[1], 2) == 1.0, "可滚动到底部（周日可见）")
        sun = tab._row["sun"][0]
        view_bottom = tab.scroll.canvas.winfo_height()
        offset = tab.scroll.canvas.yview()[0] * tab.scroll.body.winfo_reqheight()
        y_top = sun.winfo_rooty() - tab.scroll.body.winfo_rooty() - offset
        check(0 <= y_top and y_top + sun.winfo_height() <= view_bottom + 1,
              f"周日整行落在可视区内 (y={y_top:.0f}, 视口={view_bottom})")

    def step_countdown() -> None:
        from app.models import Countdown

        added = Countdown(name="单元测试倒计时", target="2099-01-01", show_in_bar=True,
                          show_desktop=True)
        ctl.data.countdowns.append(added)
        w = ctl.main_window
        w.nb.select(3)
        tab = w.tab_countdown
        tab.refresh()
        root.update()
        check(tab.tree.exists(added.id), "倒计时页出现新增行")
        check("还剩" in tab.tree.item(added.id, "values")[2], "剩余列显示天数文案")
        check(tab.lbl_hint.winfo_ismapped(), "底部统计行可见（未被表格挤掉）")
        check("共 " in tab.lbl_hint.cget("text"), f"统计文案 = {tab.lbl_hint.cget('text')}")

        ctl.topbar.refresh_countdown()
        root.update()
        check("单元测试倒计时" in ctl.topbar.lbl_cd.cget("text"), "悬浮条显示倒计时")

        ctl.data.settings["show_desktop_countdown"] = True
        ctl.sync_desktop_countdown()
        root.update()
        d = ctl.desktop_countdown
        check(d is not None and d.winfo_exists() and d.winfo_viewable(), "桌面贴纸已出现")
        check(d is not None and len(d.rows.winfo_children()) >= 1, "桌面子程序渲染了倒计时")

        ctl.data.settings["show_desktop_countdown"] = False
        ctl.sync_desktop_countdown()
        root.update()
        check(ctl.desktop_countdown is None, "关闭开关后桌面贴纸已销毁")

        ctl.data.countdowns.remove(added)
        tab.refresh()
        ctl.topbar.refresh_countdown()
        root.update()
        check(not tab.tree.exists(added.id), "清理后行已移除")

    def step4() -> None:
        ctl.toast.show("到上数学课时间了！", seconds=1)
        check(len(ctl.toast._toasts) == 1, "气泡已创建")
        check(win32util.is_click_through(ctl.toast._toasts[0]), "提醒气泡已开启穿透")

    def step5() -> None:
        check(len(ctl.toast._toasts) == 0, "气泡按时自动消失")

    def step_slots_axis() -> None:
        """今日时段条：压缩凌晨空白后，仍与 24 小时进度条共用同一条轴。"""
        from app.models import Period, new_id

        bar = ctl.topbar
        cv = bar.cv_slots
        state = bar._last_state
        sched = ctl.data.schedule_for_day(state["key"])
        keep = list(sched.periods)
        # 固定成「早课 + 大空档 + 晚课」，压缩规则才有确定的预期值
        sched.periods = [
            Period(id=new_id("p"), name="第一节", start="09:50", end="10:35", kind="class"),
            Period(id=new_id("p"), name="第二节", start="10:45", end="11:30", kind="class"),
            Period(id=new_id("p"), name="晚自习五", start="21:50", end="22:20", kind="class"),
        ]
        bar._tick()
        root.update()

        w = cv.winfo_width()
        check(w > 200 and bar.cv_day.winfo_width() == w, f"两条画布同宽 = {w}")

        axis = bar._time_axis()
        x0, x1 = axis.x0, axis.x1
        polys = [cv.bbox(i) for i in cv.find_all() if cv.type(i) == "polygon"]
        texts = [(cv.bbox(i), cv.itemcget(i, "text")) for i in cv.find_all() if cv.type(i) == "text"]
        slots = bar._last_state["slots"]
        check(len(polys) == len(slots), f"块数 = {len(polys)} / 时段 {len(slots)}")

        # 1) 时段条与进度条共用同一映射：块左沿 = axis.to_x(起秒)
        worst = 0.0
        for slot, box in zip(slots, polys):
            worst = max(worst, abs(box[0] - axis.to_x(slot.start_s)))
        check(worst <= 3, f"块位置按压缩轴换算（最大偏差 {worst:.1f}px）")

        # 2) 不越界（以前首帧用整条宽度换算，最右边的块会被画到画布外）
        check(all(0 <= b[0] and b[2] <= w for b in polys), "所有块都在画布内")

        # 3) 最窄的那一节（30 分钟）也要有文字，且文字不溢出块
        last_box = polys[-1]
        inside = [(tb, name) for tb, name in texts
                  if last_box[0] < (tb[0] + tb[2]) / 2 < last_box[2]]
        check(bool(inside), f"最窄一节有文字 = {[n for _, n in inside]}")
        if inside:
            tb = inside[0][0]
            check(last_box[0] <= tb[0] and tb[2] <= last_box[2],
                  f"文字未溢出块（文字 {tb[2]-tb[0]}px / 块 {last_box[2]-last_box[0]:.0f}px）")

        overflow = [(n, tb, b) for (tb, n) in texts for b in polys
                    if b[0] < (tb[0] + tb[2]) / 2 < b[2] and (tb[0] < b[0] or tb[2] > b[2])]
        check(not overflow, f"没有文字压出块边界 = {overflow[:2]}")

        # 4) 压缩生效：凌晨 0–9 点不再白占四分之一条，活跃时段拿到大部分宽度
        span = x1 - x0
        night = axis.to_x(9 * 3600) - axis.to_x(0)
        check(night < span * 0.12, f"00:00–09:00 只占全宽 {night / span * 100:.1f}%")
        active = axis.to_x(22 * 3600 + 20 * 60) - axis.to_x(9 * 3600 + 50 * 60)
        check(active > span * 0.75, f"活跃时段占全宽 {active / span * 100:.1f}%")

        # 5) 同为 45 分钟的两节，块宽必须相同（窗口内 1:1，时长即长度）
        w0 = polys[0][2] - polys[0][0]
        w1 = polys[1][2] - polys[1][0]
        check(abs(w0 - w1) <= 2, f"两节 45 分钟等宽（{w0:.0f} / {w1:.0f}px）")

        # 6) 整点网格跟着压缩走，且不挤在一起（「现在」那条强调色竖线不算网格）
        lines = [cv.coords(i) for i in cv.find_all()
                 if cv.type(i) == "line" and cv.itemcget(i, "fill") != theme.ACCENT]
        vertical = sorted(c[0] for c in lines if abs(c[0] - c[2]) < 0.6)
        check(len(vertical) >= 10, f"整点网格线 = {len(vertical)} 条")
        gaps = [b - a for a, b in zip(vertical, vertical[1:])]
        check(not gaps or min(gaps) >= theme.S(13) - 1,
              f"网格最密处间距 {min(gaps) if gaps else 0:.0f}px（压缩区不再堆线）")

        sched.periods = keep
        bar._tick()
        root.update()

    def step_shutdown() -> None:
        """定时关机：设置页交互 + 带按钮的气泡必须能点到（不能穿透）。"""
        ts = ctl.main_window.tab_settings
        s = ctl.data.settings

        check(ts.days.get() == [0, 1, 2, 3, 4], f"默认周一到周五 = {ts.days.get()}")
        ts.days.toggle(5)
        root.update()
        check(s["shutdown_days"] == [0, 1, 2, 3, 4, 5], f"点亮周六写入设置 = {s['shutdown_days']}")

        ts.v_sd_time.set("23:15")
        ts._apply_shutdown()
        check(s["shutdown_time"] == "23:15", "关机时间写入设置")

        ts.v_sd_time.set("99:99")
        ts._apply_shutdown()
        check(s["shutdown_time"] == "23:15" and ts.v_sd_time.get() == "23:15",
              "非法时间被退回原值，不会写进配置")

        ts.v_sd_on.set(True)
        ts._apply_shutdown()
        check(s["shutdown_enabled"] is True, "开关打开后写入设置")

        ts.days.set([])
        ts._apply_shutdown()
        check(s["shutdown_enabled"] is False and not ts.v_sd_on.get(),
              "清空星期会顺手关掉开关（否则开着却不关机）")

        # 带按钮的气泡：默认鼠标穿透开着，这种气泡必须能被点到
        ctl.toast.show("测试：电脑将在 30 秒后关闭", subtitle="定时关机", seconds=4,
                       action=lambda: None, action_label="取消关机")
        root.update()
        check(not win32util.is_click_through(ctl.toast._toasts[-1]),
              "带「取消关机」按钮的气泡不穿透")

        ctl.toast.show("普通提醒", seconds=2)
        root.update()
        check(win32util.is_click_through(ctl.toast._toasts[-1]), "普通气泡仍然穿透")
        ctl.toast.clear()
        root.update()

        # 端到端排程：runner 换成假的，这一整段测试不会真的关机
        from datetime import datetime as _dt

        from app.power import run_shutdown
        fake_now = _dt.now().replace(hour=22, minute=29, second=30, microsecond=0)
        calls: list[tuple] = []
        ctl.shutdown._run = lambda *a: (calls.append(a), True)[1]
        s.update({"shutdown_enabled": True, "shutdown_time": "22:30",
                  "shutdown_days": [fake_now.weekday()]})
        ev = ctl.shutdown.tick(fake_now, s)
        check(ev is not None and ev["seconds"] == 30, f"22:29:30 排程 → 还剩 {ev and ev['seconds']} 秒")
        check(calls == [("/s", "/t", "30")], f"假 runner 收到关机命令 {calls}（不真关机）")
        ctl.shutdown.cancel()
        check(calls[-1] == ("/a",), "取消时下发 /a")
        ctl.shutdown._run = run_shutdown

        ts.days.set([0, 1, 2, 3, 4])
        ts.v_sd_on.set(False)
        ts._apply_shutdown()

    root.after(600, step1)
    root.after(900, step_bar_area)
    root.after(1600, step2)
    root.after(2100, step3)
    root.after(2450, step_scroll)
    root.after(2850, step_countdown)
    root.after(3500, step4)
    root.after(4800, step5)
    root.after(5200, step_slots_axis)
    root.after(6100, step_shutdown)
    root.after(7200, root.destroy)
    root.mainloop()
    print("FAILED:", FAILED if FAILED else "none")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
