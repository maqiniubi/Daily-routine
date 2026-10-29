"""核心逻辑自动化测试（无界面）：数据模型、存储、周期调度、提醒触发。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 测试进程一律用临时数据目录：绝不能读写用户真实的 %APPDATA%\ClassBell
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_test_")


from app.models import (DAY_KEYS, KIND_BREAK, KIND_CLASS, AppData, Period, Schedule, default_data,
                        fmt_minutes, parse_time)
from app.scheduler import ReminderEngine, build_slots, day_key, day_state, reminder_text
from app.store import Store

PASS = 0


def check(cond: bool, label: str) -> None:
    global PASS
    if not cond:
        raise AssertionError(f"FAIL: {label}")
    PASS += 1
    print(f"  ok  {label}")


def test_models() -> None:
    print("[models]")
    check(parse_time("08:05") == 485, "parse_time")
    check(fmt_minutes(485) == "08:05", "fmt_minutes")
    try:
        parse_time("8:5")
        raise AssertionError("应当拒绝非法时间")
    except ValueError:
        check(True, "拒绝非法时间格式")

    p = Period(id="x", name="第一节", start="09:00", end="08:00", kind=KIND_CLASS)
    try:
        p.validate()
        raise AssertionError("应当拒绝倒序时间")
    except ValueError:
        check(True, "结束早于开始时校验失败")

    d = AppData(default_data())
    d.validate()
    check(len(d.schedules) == 2, "默认两张作息表")
    check(len(d.schedule_for_day("mon").periods) == 14, "默认 14 个时段")
    check(d.week["mon"] == d.schedules[0].id, "默认周一使用基础作息")


def test_store() -> None:
    print("[store]")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        st = Store(path)
        st.load()
        st.data.schedules[0].name = "教学日"
        st.data.courses["mon"] = {st.data.schedules[0].periods[0].id: "语文"}
        st.save()
        check(path.exists(), "配置文件已写入")

        st2 = Store(path)
        d2 = st2.load()
        check(d2.schedules[0].name == "教学日", "重新读取后名称保留")
        check(list(d2.courses["mon"].values()) == ["语文"], "课程表持久化")

        out = Path(tmp) / "export.json"
        st2.export_to(str(out))
        raw = json.loads(out.read_text(encoding="utf-8"))
        check("schedules" in raw and "week" in raw and "courses" in raw, "导出 JSON 结构完整")

        st3 = Store(Path(tmp) / "other.json")
        st3.import_from(str(out))
        check(st3.data.schedules[0].name == "教学日", "导入后数据一致")

        bad = Path(tmp) / "bad.json"
        bad.write_text("[]", encoding="utf-8")
        try:
            st3.import_from(str(bad))
            raise AssertionError("应当拒绝非法文件")
        except ValueError:
            check(True, "拒绝非法导入文件")


def test_scheduler() -> None:
    print("[scheduler]")
    d = AppData(default_data())
    base = d.schedules[0]
    p1 = next(p for p in base.periods if p.name == "第一节")
    d.courses["mon"] = {p1.id: "数学"}

    check(day_key(date(2026, 10, 26)) == "mon", "2026-10-26 是周一")

    slots = build_slots(d, "mon")
    check(len(slots) == 14, "周一解析出 14 个时段")
    check(slots[0].period.name == "早读", "按开始时间排序")
    check(slots[1].course == "数学", "时段绑定课程")

    at_start = datetime(2026, 10, 26, 8, 0, 2)
    st = day_state(d, at_start)
    check(st["current"] is not None and st["current"].course == "数学", "当前时段识别为第一节")
    check(st["next"] is not None and st["next"].period.name == "第二节", "下一节识别正确")

    # 周三切换到特殊作息
    special = d.schedules[1]
    d.week["wed"] = special.id
    check(d.schedule_for_day("wed").id == special.id, "周三切到特殊作息")
    check(len(build_slots(d, "wed")) == 5, "特殊作息 5 个时段")

    # 提醒文案
    check(reminder_text(slots[1], "start") == "到上数学课时间了！", "上课提醒文案")
    check(reminder_text(slots[1], "end") == "到下课时间了！", "下课提醒文案")
    check(reminder_text(slots[0], "start") == "到早读时间了！", "非课程时段文案")
    slots_art = build_slots(d, "mon")
    art = next(s for s in slots_art if s.period.kind == KIND_BREAK)
    check(reminder_text(art, "start").startswith("到"), "课间提醒文案可用")


def test_reminder_engine() -> None:
    print("[reminder]")
    d = AppData(default_data())
    base = d.schedules[0]
    p1 = next(p for p in base.periods if p.name == "第一节")
    d.courses["mon"] = {p1.id: "数学"}
    fired: list[tuple[str, str]] = []
    eng = ReminderEngine(d, lambda text, slot, phase: fired.append((text, phase)))

    start = datetime(2026, 10, 26, 8, 0, 0)
    eng.tick(start - timedelta(seconds=1))
    check(len(fired) == 0, "节点前不触发")
    eng.tick(start + timedelta(seconds=1))
    check(fired and fired[0][0] == "到上数学课时间了！", "到点触发上课提醒")
    eng.tick(start + timedelta(seconds=2))
    check(len(fired) == 1, "同一节点只触发一次")

    end = datetime(2026, 10, 26, 8, 45, 0)
    eng.tick(end + timedelta(seconds=1))
    check(fired[-1][0] == "到下课时间了！" and fired[-1][1] == "end", "下课时触发下课提醒")

    # 中途启动不应补报历史节点
    fired.clear()
    eng2 = ReminderEngine(d, lambda text, slot, phase: fired.append((text, phase)))
    eng2.tick(datetime(2026, 10, 26, 12, 0, 0))
    check(len(fired) == 0, "中途启动不补报历史提醒")

    # 关闭提醒开关
    fired.clear()
    d.settings["reminders_enabled"] = False
    eng3 = ReminderEngine(d, lambda text, slot, phase: fired.append((text, phase)))
    eng3.tick(datetime(2026, 10, 26, 8, 0, 1))
    check(len(fired) == 0, "关闭开关后不提醒")
    d.settings["reminders_enabled"] = True

    # 跨天重置
    fired.clear()
    eng4 = ReminderEngine(d, lambda text, slot, phase: fired.append((text, phase)))
    eng4.tick(datetime(2026, 10, 26, 8, 0, 1))
    n1 = len(fired)
    eng4.tick(datetime(2026, 10, 27, 8, 0, 1))
    check(n1 == 1 and len(fired) == 2, "跨天后可再次触发")


def test_countdown() -> None:
    print("[countdown]")
    from app.models import Countdown

    base = date(2026, 10, 28)

    cd = Countdown(name="期末考试", target="2026-11-08", show_in_bar=True, show_desktop=True)
    check(cd.target_date() == date(2026, 11, 8), "解析 YYYY-MM-DD")
    check(Countdown(target="2026/11/08").target_date() == date(2026, 11, 8), "兼容斜杠写法")
    check(Countdown(target="2026-11-08 09:30").target_date() == date(2026, 11, 8), "忽略具体时刻")
    check(Countdown(target="").target_date() is None, "空日期返回 None")
    check(Countdown(target="2026-13-40").target_date() is None, "非法日期返回 None")

    check(cd.days_left(base) == 11, "未来日期天数")
    check(cd.phrase(base) == "还剩 11 天", "未来文案")
    check(cd.short(base) == "期末考试 11天", "悬浮条紧凑文案")
    check(Countdown(name="生日", target="2026-10-28").phrase(base) == "就是今天", "当天文案")
    check(Countdown(name="开学", target="2026-10-25").phrase(base) == "已过 3 天", "过期文案")
    check(Countdown(name="开学", target="2026-10-25").short(base) == "开学 已过3天", "过期紧凑文案")

    try:
        Countdown(name="  ", target="2026-10-28").validate()
        raise AssertionError("应当拒绝空名称")
    except ValueError:
        check(True, "空名称校验失败")
    try:
        Countdown(name="x", target="明年").validate()
        raise AssertionError("应当拒绝非法日期")
    except ValueError:
        check(True, "非法日期校验失败")

    raw = {"id": "c1", "name": "高考", "target": "2027-06-07",
           "show_in_bar": False, "show_desktop": True, "pos": [12, 34]}
    rt = Countdown.from_dict(raw)
    check(rt.to_dict() == raw, "序列化往返一致")
    check(Countdown.from_dict({"name": "x", "pos": "bad"}).pos == [80, 96], "坏坐标回落到默认")

    d = AppData(default_data())
    d.countdowns = [
        Countdown(name="远", target="2027-12-31", show_in_bar=True, show_desktop=False),
        Countdown(name="近", target="2026-11-01", show_in_bar=True, show_desktop=True),
        Countdown(name="中", target="2026-12-01", show_in_bar=True, show_desktop=False),
        Countdown(name="未设", target="", show_in_bar=True, show_desktop=True),
    ]
    bar = d.bar_countdowns(limit=2)
    check([c.name for c in bar] == ["近", "中"], "悬浮条按剩余天数取最近的两个")
    check([c.name for c in d.desktop_countdowns()] == ["近"], "桌面贴纸只收已设日期且勾选的")
    d.settings["show_desktop_countdown"] = True
    d.validate()
    check(len(d.countdowns) == 4, "校验后倒计时数量不变")

    with tempfile.TemporaryDirectory() as tmp:
        st = Store(Path(tmp) / "config.json")
        st.data = d
        st.save()
        again = Store(Path(tmp) / "config.json").load()
        check([c.name for c in again.countdowns] == ["远", "近", "中", "未设"], "倒计时可持久化")
        check(again.settings.get("show_desktop_countdown") is True, "桌面开关可持久化")


def test_progress() -> None:
    print("[progress]")
    for hh, mm, expect in ((0, 0, 0.0), (12, 0, 0.5), (23, 59, 0.9993)):
        now = datetime(2026, 10, 28, hh, mm, 0)
        sec = now.hour * 3600 + now.minute * 60 + now.second
        ratio = sec / 86400
        check(abs(ratio - expect) < 0.001, f"{hh:02d}:{mm:02d} 进度 {ratio:.4f}")


if __name__ == "__main__":
    test_models()
    test_store()
    test_scheduler()
    test_reminder_engine()
    test_countdown()
    test_progress()
    print(f"\nALL PASSED ({PASS} checks)")
