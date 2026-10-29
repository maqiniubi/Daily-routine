"""调度与提醒：把「某天的作息表 + 该天课程表」解析成时间轴，并驱动节点提醒。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .models import DAY_KEYS, KIND_CLASS, AppData, Period, parse_time


@dataclass
class Slot:
    """时间轴上的一个时段（已绑定当天课程）。"""

    period: Period
    course: str
    start_s: int  # 当日秒数
    end_s: int

    @property
    def is_class(self) -> bool:
        return self.period.kind == KIND_CLASS

    def label(self) -> str:
        return self.course or self.period.name


def day_key(d: date | datetime) -> str:
    return DAY_KEYS[d.weekday()]


def build_slots(data: AppData, key: str) -> list[Slot]:
    """解析某天的时间轴，按开始时间升序。"""
    sched = data.schedule_for_day(key)
    courses = data.courses_for_day(key)
    slots: list[Slot] = []
    for p in sched.sorted_periods():
        try:
            s, e = parse_time(p.start), parse_time(p.end)
        except ValueError:
            continue
        slots.append(Slot(period=p, course=(courses.get(p.id) or "").strip(), start_s=s * 60, end_s=e * 60))
    return slots


def seconds_of_day(now: datetime) -> int:
    return now.hour * 3600 + now.minute * 60 + now.second


def day_state(data: AppData, now: datetime) -> dict:
    """当前时刻的完整状态：用于悬浮条渲染与提醒。"""
    key = day_key(now)
    slots = build_slots(data, key)
    sec = seconds_of_day(now)

    current = None
    for slot in slots:
        if slot.start_s <= sec < slot.end_s:
            current = slot
            break

    upcoming = next((s for s in slots if s.start_s > sec), None)
    return {
        "key": key,
        "slots": slots,
        "sec": sec,
        "current": current,
        "next": upcoming,
        "rest": (upcoming.start_s - sec) if upcoming else 0,
        "left": (current.end_s - sec) if current else 0,
        "finished": bool(slots) and sec >= slots[-1].end_s,
    }


def hhmmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def hhmm(seconds: int) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def reminder_text(slot: Slot, phase: str) -> str:
    """生成提醒文案：phase = start / end。"""
    if phase == "end":
        return "到下课时间了！"
    if slot.is_class and slot.course:
        name = slot.course
        return f"到上{name}时间了！" if name.endswith("课") else f"到上{name}课时间了！"
    return f"到{slot.period.name}时间了！"


class ReminderEngine:
    """按秒轮询触发节点提醒；同一天同一节点只触发一次。"""

    LATE_TOLERANCE = 5  # 允许 5 秒的调度抖动；超过说明程序是中途启动的，不补报

    def __init__(self, data: AppData, emit):
        self.data = data
        self.emit = emit
        self._today: date | None = None
        self._fired: set[tuple] = set()
        self._slots_cache: list[Slot] = []

    def reset(self) -> None:
        self._today = None
        self._fired.clear()
        self._slots_cache = []

    def tick(self, now: datetime) -> None:
        today = now.date()
        if today != self._today:
            self._today = today
            self._fired.clear()
            self._slots_cache = build_slots(self.data, day_key(now))

        settings = self.data.settings
        if not settings.get("reminders_enabled", True):
            return

        sec = seconds_of_day(now)
        for slot in self._slots_cache:
            if self._due(sec, slot.start_s):
                key = (today, slot.period.id, "start")
                if key not in self._fired:
                    self._fired.add(key)
                    self.emit(reminder_text(slot, "start"), slot, "start")

            if slot.is_class and settings.get("remind_period_end", True) and self._due(sec, slot.end_s):
                key = (today, slot.period.id, "end")
                if key not in self._fired:
                    self._fired.add(key)
                    self.emit(reminder_text(slot, "end"), slot, "end")

    @classmethod
    def _due(cls, now_sec: int, target: int) -> bool:
        return 0 <= now_sec - target <= cls.LATE_TOLERANCE
