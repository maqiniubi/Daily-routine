"""定时关机逻辑测试（无界面、绝不真的关机）。

`ShutdownScheduler` 的 runner 注入假函数，只记录收到的 argv，
所以这一整套测试跑在任何机器上都不会触发系统关机。
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_power_test_")

from app.models import AppData, default_data, default_settings  # noqa: E402
from app.power import (MIN_LEAD_SECONDS, ShutdownScheduler, format_hhmm, normalize_days,  # noqa: E402
                       parse_hhmm)

PASS = 0


def check(cond: bool, label: str) -> None:
    global PASS
    if not cond:
        raise AssertionError(f"FAIL: {label}")
    PASS += 1
    print(f"  ok  {label}")


class FakeRunner:
    """记录调用，永远成功。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, *args: str) -> bool:
        self.calls.append(args)
        return True

    def clear(self) -> None:
        self.calls.clear()


def settings(**over) -> dict:
    s = default_settings()
    s.update({
        "shutdown_enabled": True,
        "shutdown_time": "22:30",
        "shutdown_days": [0, 1, 2, 3, 4, 5, 6],
        "shutdown_notice_min": 1,
    })
    s.update(over)
    return s


#: 2026-10-26 是周一
MON = datetime(2026, 10, 26, 22, 29, 0)


def test_parse() -> None:
    print("[时间解析]")
    check(parse_hhmm("22:30") == (22, 30), "22:30 → (22, 30)")
    check(parse_hhmm(" 7:5 ") == (7, 5), "宽松输入 7:5 → (7, 5)")
    check(parse_hhmm("22：30") == (22, 30), "全角冒号也能读")
    check(parse_hhmm("24:00") is None, "24:00 越界 → None")
    check(parse_hhmm("22:70") is None, "22:70 越界 → None")
    check(parse_hhmm("abc") is None, "乱输 → None")
    check(parse_hhmm("") is None, "空串 → None")
    check(format_hhmm("7:5") == "07:05", "format 补零 → 07:05")
    check(format_hhmm("乱写") == "22:30", "非法输入退回 22:30")


def test_days() -> None:
    print("[星期清洗]")
    check(normalize_days([4, 0, 0, 2]) == [0, 2, 4], "排序去重")
    check(normalize_days([7, -1, 3]) == [3], "越界值丢弃")
    check(normalize_days(["1", 2]) == [1, 2], "字符串数字也认")
    check(normalize_days(None) == [], "None → 空")
    check(normalize_days(["x", 1.9]) == [1], "非数字丢弃、浮点截断")


def test_disabled() -> None:
    print("[未启用]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)
    check(sched.tick(MON, settings(shutdown_enabled=False)) is None, "关闭时不下命令")
    check(run.calls == [], "runner 未被调用")


def test_arm_flow() -> None:
    print("[到点前排程]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)

    early = datetime(2026, 10, 26, 22, 28, 59)        # 还剩 61 秒，还在提醒窗口外
    check(sched.tick(early, settings()) is None, "距目标 61 秒 → 还没到提醒窗口，不下命令")
    check(run.calls == [], "窗口外不调用 runner")

    run.clear()
    soon = datetime(2026, 10, 26, 22, 29, 30)         # 还剩 30 秒
    ev = sched.tick(soon, settings())
    check(ev is not None and ev["kind"] == "notice", "进入提醒窗口 → 返回 notice 事件")
    check(ev["seconds"] == 30, f"事件里带剩余秒数 = {ev and ev['seconds']}")
    check(run.calls[-1] == ("/s", "/t", "30"), f"下达 shutdown /s /t 30 → {run.calls[-1]}")
    check(sched.armed_at is not None, "已记录排程目标时刻")

    run.clear()
    check(sched.tick(soon + timedelta(seconds=5), settings()) is None, "同一目标不重复下命令")
    check(run.calls == [], "重复 tick 没有多余调用")

    sched.tick(datetime(2026, 10, 26, 22, 31, 0), settings())   # 过点
    check(sched.armed_at is None, "过点后清掉排程状态（不补关）")


def test_too_late() -> None:
    print("[太晚启动就不关]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)
    nearly = datetime(2026, 10, 26, 22, 29, 60 - MIN_LEAD_SECONDS + 2)   # 只剩 13 秒
    check(sched.tick(nearly, settings()) is None, "剩余不足 15 秒 → 放弃今天")
    check(run.calls == [], "没有下达任何关机命令")


def test_weekday_filter() -> None:
    print("[星期过滤]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)
    s = settings(shutdown_days=[0, 1, 2, 3, 4])       # 仅工作日
    check(sched.tick(datetime(2026, 10, 31, 22, 29, 40), s) is None, "周六不生效")
    check(run.calls == [], "周六不下命令")
    ev = sched.tick(datetime(2026, 11, 2, 22, 29, 40), s)   # 周一
    check(ev is not None, "周一正常排程")


def test_change_time_cancels() -> None:
    print("[改时间 / 关开关会先撤销]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)
    sched.tick(datetime(2026, 10, 26, 22, 29, 40), settings())
    check(sched.armed_at is not None, "先排上程")

    run.clear()
    sched.tick(datetime(2026, 10, 26, 22, 29, 45), settings(shutdown_time="23:00"))
    check(run.calls and run.calls[0] == ("/a",), f"改时间先 /a → {run.calls}")
    check(sched.armed_at is None, "旧排程作废")

    run.clear()
    sched.tick(datetime(2026, 10, 26, 22, 29, 40), settings())
    check(sched.armed_at is not None, "重新排上程")
    run.clear()
    sched.tick(datetime(2026, 10, 26, 22, 29, 45), settings(shutdown_enabled=False))
    check(run.calls and run.calls[0] == ("/a",), "关闭开关 → 立即撤销")


def test_manual_cancel() -> None:
    print("[手动取消]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)
    sched.tick(datetime(2026, 10, 26, 22, 29, 40), settings())
    run.clear()
    check(sched.cancel() is True, "cancel() 返回成功")
    check(run.calls == [("/a",)], "下发 shutdown /a")
    check(sched.armed_at is None, "状态已清空")
    run.clear()
    sched.cancel()
    check(run.calls == [("/a",)], "没有排程时再取消也只是 /a，无副作用")


def test_rollover() -> None:
    print("[跨天]")
    run = FakeRunner()
    sched = ShutdownScheduler(run)
    sched.tick(datetime(2026, 10, 26, 22, 29, 40), settings())
    run.clear()
    # 第二天 22:29:40 再排程：跨天后目标时刻不同，旧的先撤销再排新的
    ev = sched.tick(datetime(2026, 10, 27, 22, 29, 40), settings())
    check(ev is not None, "次日重新排程")
    check(("/a",) in run.calls, f"先把昨天的作废 → {run.calls}")


def test_describe() -> None:
    print("[状态文案]")
    sched = ShutdownScheduler(FakeRunner())
    check(sched.describe(settings(shutdown_enabled=False)) == "未启用", "关闭时文案")
    check(sched.describe(settings(shutdown_days=[])) == "未选择星期，不会关机", "空星期文案")
    text = sched.describe(settings())
    check("22:30" in text and "每天" in text, f"全周文案 = {text}")
    workday = sched.describe(settings(shutdown_days=[0, 1, 2, 3, 4]))
    check("周一至周五" in workday, f"工作日文案 = {workday}")
    odd = sched.describe(settings(shutdown_days=[0, 3]))
    check("周一" in odd and "周四" in odd, f"零散选择逐个列出 = {odd}")


def test_settings_sanitize() -> None:
    print("[配置清洗]")
    raw = default_data()          # AppData 要求带 schedules，否则整体回落到默认数据
    raw["settings"].update({"shutdown_time": "9:7", "shutdown_days": [3, 3, 9, "1"],
                            "shutdown_notice_min": 999})
    data = AppData(raw)
    check(data.settings["shutdown_time"] == "09:07", "时间被规范化")
    check(data.settings["shutdown_days"] == [1, 3], "星期被清洗")
    check(data.settings["shutdown_notice_min"] == 30, "提前量夹到上限 30")
    fresh = AppData({})
    check(fresh.settings["shutdown_enabled"] is False, "老配置默认不开定时关机")
    check(fresh.settings["shutdown_days"] == [0, 1, 2, 3, 4], "默认周一到周五")


if __name__ == "__main__":
    test_parse()
    test_days()
    test_disabled()
    test_arm_flow()
    test_too_late()
    test_weekday_filter()
    test_change_time_cancels()
    test_manual_cancel()
    test_rollover()
    test_describe()
    test_settings_sanitize()
    print(f"\nALL PASSED ({PASS} checks)")
