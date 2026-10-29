"""数据模型与校验：作息表 / 时段 / 周安排 / 课程表 / 设置。"""
from __future__ import annotations

import copy
import re
import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

from .palette import BAR_SLOTS, DEFAULT_BAR, DEFAULT_UI, UI_SLOTS, normalize_theme
from .power import format_hhmm, normalize_days

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

KIND_CLASS = "class"
KIND_BREAK = "break"
KIND_OTHER = "other"
KIND_LABELS = {KIND_CLASS: "上课", KIND_BREAK: "课间", KIND_OTHER: "其它"}
KIND_BY_LABEL = {v: k for k, v in KIND_LABELS.items()}

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def new_id(prefix: str = "p") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def parse_time(text: str) -> int:
    """'HH:MM' -> 当日分钟数；非法抛 ValueError。"""
    m = _TIME_RE.match(str(text).strip())
    if not m:
        raise ValueError(f"时间格式不正确：{text}（应为 HH:MM，如 08:00）")
    return int(m.group(1)) * 60 + int(m.group(2))


def fmt_minutes(minutes: int) -> str:
    minutes = max(0, min(24 * 60, int(minutes)))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Period:
    """一个作息时段。"""

    id: str = field(default_factory=lambda: new_id("p"))
    name: str = "新时段"
    start: str = "08:00"
    end: str = "08:45"
    kind: str = KIND_CLASS

    @property
    def start_min(self) -> int:
        return parse_time(self.start)

    @property
    def end_min(self) -> int:
        return parse_time(self.end)

    def duration_min(self) -> int:
        return max(0, self.end_min - self.start_min)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "start": self.start, "end": self.end, "kind": self.kind}

    @classmethod
    def from_dict(cls, raw: dict) -> "Period":
        kind = str(raw.get("kind", KIND_CLASS))
        if kind not in KIND_LABELS:
            kind = KIND_CLASS
        return cls(
            id=str(raw.get("id") or new_id("p")),
            name=str(raw.get("name") or "未命名"),
            start=str(raw.get("start") or "08:00"),
            end=str(raw.get("end") or "08:45"),
            kind=kind,
        )

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("时段名称不能为空")
        if len(self.name.strip()) > 20:
            raise ValueError("时段名称请控制在 20 字以内")
        s, e = parse_time(self.start), parse_time(self.end)
        if e <= s:
            raise ValueError(f"「{self.name}」结束时间必须晚于开始时间")


@dataclass
class Schedule:
    """一张完整的作息时间表。"""

    id: str = field(default_factory=lambda: new_id("s"))
    name: str = "新作息表"
    periods: list[Period] = field(default_factory=list)

    def sorted_periods(self) -> list[Period]:
        return sorted(self.periods, key=lambda p: (parse_time(p.start), parse_time(p.end)))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "periods": [p.to_dict() for p in self.sorted_periods()]}

    @classmethod
    def from_dict(cls, raw: dict) -> "Schedule":
        periods = [Period.from_dict(p) for p in raw.get("periods", []) if isinstance(p, dict)]
        return cls(
            id=str(raw.get("id") or new_id("s")),
            name=str(raw.get("name") or "未命名作息"),
            periods=periods,
        )

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("作息表名称不能为空")
        ids = set()
        for p in self.periods:
            p.validate()
            if p.id in ids:
                p.id = new_id("p")
            ids.add(p.id)


@dataclass
class Countdown:
    """一个倒计时目标（如「高考倒计时」）。日期按自然日计算，与时刻无关。"""

    id: str = field(default_factory=lambda: new_id("c"))
    name: str = "倒计时"
    target: str = ""              # "YYYY-MM-DD" 或 "YYYY-MM-DD HH:MM"
    show_in_bar: bool = True      # 显示在顶部悬浮条
    show_desktop: bool = False    # 显示在桌面贴纸
    pos: list = field(default_factory=lambda: [80, 96])

    # ---------- 计算 ----------
    def target_date(self) -> "date | None":
        text = str(self.target).strip().replace("/", "-")
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def days_left(self, today: "date | None" = None) -> int | None:
        d = self.target_date()
        if d is None:
            return None
        base = today or datetime.now().date()
        return (d - base).days

    def phrase(self, today: "date | None" = None) -> str:
        """「还剩 12 天」/「就是今天」/「已过 3 天」。"""
        n = self.days_left(today)
        if n is None:
            return "未设置日期"
        if n > 0:
            return f"还剩 {n} 天"
        if n == 0:
            return "就是今天"
        return f"已过 {abs(n)} 天"

    def short(self, today: "date | None" = None) -> str:
        """悬浮条用的紧凑形式：「高考 12天」。"""
        n = self.days_left(today)
        if n is None:
            return f"{self.name} 未设日期"
        if n > 0:
            return f"{self.name} {n}天"
        if n == 0:
            return f"{self.name} 今天"
        return f"{self.name} 已过{abs(n)}天"

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "target": self.target,
            "show_in_bar": bool(self.show_in_bar), "show_desktop": bool(self.show_desktop),
            "pos": [int(self.pos[0]), int(self.pos[1])] if isinstance(self.pos, (list, tuple)) and len(self.pos) >= 2 else [80, 96],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Countdown":
        pos = raw.get("pos")
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            pos = [80, 96]
        try:
            pos = [int(pos[0]), int(pos[1])]
        except Exception:
            pos = [80, 96]
        return cls(
            id=str(raw.get("id") or new_id("c")),
            name=str(raw.get("name") or "倒计时")[:24],
            target=str(raw.get("target") or ""),
            show_in_bar=bool(raw.get("show_in_bar", True)),
            show_desktop=bool(raw.get("show_desktop", False)),
            pos=pos,
        )

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("倒计时名称不能为空")
        if len(self.name.strip()) > 24:
            raise ValueError("倒计时名称请控制在 24 字以内")
        if self.target.strip() and self.target_date() is None:
            raise ValueError("目标日期格式应为 2026-06-07 或 2026-06-07 09:00")


def default_settings() -> dict:
    return {
        "reminders_enabled": True,
        "reminder_seconds": 5,
        "remind_period_end": True,
        "show_24h_bar": True,
        "show_slot_bar": True,
        "font_scale": 1.0,
        "course_area_h": 56,
        "click_through": True,
        "autostart": False,
        "topmost_guard_ms": 1000,
        "show_desktop_countdown": False,
        "desktop_pos": None,
        "tray_notice_shown": False,
        # 定时关机（默认关闭，必须用户显式打开；周一到周五是教室/宿舍最常见的组合）
        "shutdown_enabled": False,
        "shutdown_time": "22:30",
        "shutdown_days": [0, 1, 2, 3, 4],
        "shutdown_notice_min": 1,
        # 外观自定义：只存锚点色 + 不透明度，派生色每次启动重算
        "ui_theme": dict(DEFAULT_UI),
        "bar_theme": dict(DEFAULT_BAR),
        "ui_alpha": 1.0,
        "bar_alpha": 0.86,
    }


def _days_ahead(days: int) -> str:
    from datetime import timedelta

    return (datetime.now().date() + timedelta(days=days)).strftime("%Y-%m-%d")


def _p(name: str, start: str, end: str, kind: str) -> dict:
    return {"id": new_id("p"), "name": name, "start": start, "end": end, "kind": kind}


def default_data() -> dict:
    """首次运行的默认数据：一套中学作息 + 一个特殊作息示例 + 空白课程表。"""
    base = {
        "id": "base",
        "name": "基础作息",
        "periods": [
            _p("早读", "07:30", "07:50", KIND_OTHER),
            _p("第一节", "08:00", "08:45", KIND_CLASS),
            _p("第二节", "08:55", "09:40", KIND_CLASS),
            _p("大课间", "09:40", "10:10", KIND_BREAK),
            _p("第三节", "10:10", "10:55", KIND_CLASS),
            _p("第四节", "11:05", "11:50", KIND_CLASS),
            _p("午休", "11:50", "13:30", KIND_BREAK),
            _p("第五节", "13:30", "14:15", KIND_CLASS),
            _p("第六节", "14:25", "15:10", KIND_CLASS),
            _p("第七节", "15:20", "16:05", KIND_CLASS),
            _p("第八节", "16:15", "17:00", KIND_CLASS),
            _p("课外活动", "17:00", "18:30", KIND_OTHER),
            _p("晚自习一", "18:40", "19:25", KIND_CLASS),
            _p("晚自习二", "19:35", "20:20", KIND_CLASS),
        ],
    }
    special = {
        "id": "special_wed",
        "name": "周三半天（示例）",
        "periods": [
            _p("早读", "07:30", "07:50", KIND_OTHER),
            _p("第一节", "08:00", "08:45", KIND_CLASS),
            _p("第二节", "08:55", "09:40", KIND_CLASS),
            _p("社团活动", "09:50", "11:20", KIND_OTHER),
            _p("午餐", "11:20", "12:30", KIND_BREAK),
        ],
    }
    return {
        "version": 1,
        "settings": default_settings(),
        "schedules": [base, special],
        "week": {day: "base" for day in DAY_KEYS},
        "courses": {day: {} for day in DAY_KEYS},
        "countdowns": [
            {"id": new_id("c"), "name": "期末考试", "target": _days_ahead(30),
             "show_in_bar": True, "show_desktop": False, "pos": [80, 96]},
        ],
    }


class AppData:
    """整个应用的数据容器（对应一个 config.json）。"""

    def __init__(self, raw: dict | None = None):
        raw = raw if isinstance(raw, dict) else default_data()
        if not raw.get("schedules"):
            raw = default_data()

        self.version = int(raw.get("version") or 1)
        settings = default_settings()
        settings.update({k: v for k, v in (raw.get("settings") or {}).items() if k in settings})
        try:
            settings["reminder_seconds"] = max(1, min(30, int(settings["reminder_seconds"])))
            settings["font_scale"] = max(0.7, min(1.6, float(settings["font_scale"])))
            settings["topmost_guard_ms"] = max(300, min(10000, int(settings["topmost_guard_ms"])))
            settings["course_area_h"] = max(28, min(96, int(settings["course_area_h"])))
            # 定时关机：手改 JSON 写错了也不能让 tick 抛异常
            settings["shutdown_days"] = normalize_days(settings.get("shutdown_days"))
            settings["shutdown_time"] = format_hhmm(settings.get("shutdown_time"))
            settings["shutdown_notice_min"] = max(1, min(30, int(
                settings.get("shutdown_notice_min", 1))))
            # 外观：手改 JSON 写了非法颜色也只是回落到出厂值，不会让界面画不出来
            settings["ui_theme"] = normalize_theme(settings.get("ui_theme"), UI_SLOTS, DEFAULT_UI)
            settings["bar_theme"] = normalize_theme(settings.get("bar_theme"), BAR_SLOTS, DEFAULT_BAR)
            settings["ui_alpha"] = round(max(0.75, min(1.0, float(settings["ui_alpha"]))), 2)
            settings["bar_alpha"] = round(max(0.55, min(1.0, float(settings["bar_alpha"]))), 2)
        except Exception:
            settings = default_settings()
        self.settings: dict = settings

        self.schedules: list[Schedule] = [Schedule.from_dict(s) for s in raw.get("schedules", [])]

        week_raw = raw.get("week") or {}
        self.week: dict[str, str] = {}
        for day in DAY_KEYS:
            sid = str(week_raw.get(day) or "")
            if not self.get_schedule(sid):
                sid = self.schedules[0].id
            self.week[day] = sid

        courses_raw = raw.get("courses") or {}
        self.courses: dict[str, dict[str, str]] = {}
        for day in DAY_KEYS:
            table = courses_raw.get(day) or {}
            self.courses[day] = {str(k): str(v) for k, v in table.items() if str(v).strip()}

        self.countdowns: list[Countdown] = [
            Countdown.from_dict(c) for c in (raw.get("countdowns") or []) if isinstance(c, dict)
        ]

    # ---------- 查询 ----------
    def get_schedule(self, sid: str) -> Schedule | None:
        for s in self.schedules:
            if s.id == sid:
                return s
        return None

    def schedule_for_day(self, day_key: str) -> Schedule:
        return self.get_schedule(self.week.get(day_key, "")) or self.schedules[0]

    def courses_for_day(self, day_key: str) -> dict[str, str]:
        return self.courses.setdefault(day_key, {})

    def schedule_names(self) -> list[str]:
        return [s.name for s in self.schedules]

    # ---------- 倒计时 ----------
    def get_countdown(self, cid: str) -> Countdown | None:
        for c in self.countdowns:
            if c.id == cid:
                return c
        return None

    def bar_countdowns(self, limit: int = 2) -> list[Countdown]:
        """悬浮条展示：按剩余天数升序，优先未过期的。"""
        today = datetime.now().date()
        items = [c for c in self.countdowns if c.show_in_bar and c.target_date()]
        items.sort(key=lambda c: (c.days_left(today) or 0) < 0)
        items.sort(key=lambda c: abs(c.days_left(today) or 0))
        return items[:limit]

    def desktop_countdowns(self) -> list[Countdown]:
        today = datetime.now().date()
        items = [c for c in self.countdowns if c.show_desktop and c.target_date()]
        return sorted(items, key=lambda c: (c.days_left(today) or 0))

    # ---------- 序列化 ----------
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "settings": dict(self.settings),
            "schedules": [s.to_dict() for s in self.schedules],
            "week": dict(self.week),
            "courses": {d: dict(v) for d, v in self.courses.items()},
            "countdowns": [c.to_dict() for c in self.countdowns],
        }

    def clone(self) -> "AppData":
        return AppData(copy.deepcopy(self.to_dict()))

    def validate(self) -> None:
        if not self.schedules:
            raise ValueError("至少需要保留一张作息表")
        names = set()
        for s in self.schedules:
            s.validate()
            if s.name in names:
                raise ValueError(f"作息表名称重复：{s.name}")
            names.add(s.name)
        for day in DAY_KEYS:
            if not self.get_schedule(self.week.get(day, "")):
                raise ValueError(f"{DAY_NAMES[DAY_KEYS.index(day)]} 未指定有效作息表")
        ids = set()
        for c in self.countdowns:
            c.validate()
            if c.id in ids:
                c.id = new_id("c")
            ids.add(c.id)
        valid_ids = {p.id for s in self.schedules for p in s.periods}
        for day, table in self.courses.items():
            for pid in list(table.keys()):
                if pid not in valid_ids:
                    table.pop(pid, None)

    def cleanup_courses(self) -> None:
        """清理已删除时段对应的课程记录。"""
        valid = {p.id for s in self.schedules for p in s.periods}
        for table in self.courses.values():
            for pid in list(table.keys()):
                if pid not in valid:
                    table.pop(pid, None)

    def day_summary(self, day_key: str) -> str:
        sched = self.schedule_for_day(day_key)
        n = len(self.courses_for_day(day_key))
        return f"{sched.name} · {len(sched.periods)} 个时段" + (f" · 已排 {n} 节课" if n else " · 未排课")


def as_dict_safe(data: Any) -> dict:
    return data if isinstance(data, dict) else {}
