"""定时关机：把「每天某个时刻、某几个星期」翻译成 Windows 的一次性关机排程。

为什么不自己计时到点再关
------------------------
到点前 `notice` 分钟就交给系统的 `shutdown.exe /s /t N` 排程，好处是：
Windows 自己会有倒计时提示，即使本程序卡住/被结束，关机语义也不会变成「悄无声息」；
撤销只需一条 `shutdown /a`，比我们自己维护定时器再杀进程安全得多。

安全边界（都是踩过的坑，改动请保留）
------------------------------------
1. **默认关闭**，必须用户在设置中心显式打开；
2. 排程前一定先弹气泡，气泡上带「取消关机」按钮 —— 误触发也能挽回；
3. 剩余时间不足 `MIN_LEAD_SECONDS`（15 秒）就**放弃今天**：比突然黑屏更礼貌；
4. **退出程序时撤销排程**（`Controller._shutdown` 里调用 `cancel()`），
   否则会出现「软件关了、电脑还是关了」这种最难解释的现象；
5. 本模块只调用 `shutdown.exe`，不碰需要管理员权限的 API，也不做「立即关机」的捷径。
"""
from __future__ import annotations

import subprocess
from datetime import datetime

#: 不弹控制台窗口（`--windowed` 打包后 subprocess 默认会闪一个黑框）
_CREATE_NO_WINDOW = 0x08000000

#: 剩余时间少于这么多秒就不排程了：突然关机会打断正在做的事
MIN_LEAD_SECONDS = 15

#: 星期序号与 `datetime.weekday()` 一致：0 = 周一 … 6 = 周日
WEEK_LABELS = ("一", "二", "三", "四", "五", "六", "日")


def normalize_days(raw) -> list[int]:
    """把任意输入洗成有序去重的 0~6 列表；非法值直接丢掉。"""
    out: list[int] = []
    for value in raw or []:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6 and day not in out:
            out.append(day)
    return sorted(out)


def parse_hhmm(text) -> tuple[int, int] | None:
    """`"22:30"` / `"22：30"` / `" 7:5 "` → (时, 分)；非法返回 None。"""
    try:
        parts = str(text).strip().replace("：", ":").replace(".", ":").split(":")
        hour, minute = int(parts[0]), int(parts[1])
    except (IndexError, TypeError, ValueError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour, minute
    return None


def format_hhmm(text, fallback: str = "22:30") -> str:
    """统一成 `HH:MM`，非法输入退回 fallback（用于清洗配置文件）。"""
    parsed = parse_hhmm(text)
    if parsed is None:
        return fallback
    return f"{parsed[0]:02d}:{parsed[1]:02d}"


def run_shutdown(*args: str) -> bool:
    """调用系统 shutdown.exe。失败只返回 False，绝不抛异常打断 tick 链。"""
    try:
        subprocess.run(["shutdown", *args], creationflags=_CREATE_NO_WINDOW,
                       timeout=8, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
        return True
    except Exception:
        return False


class ShutdownScheduler:
    """每秒喂一次 `tick()`，只在需要时向系统下一条排程。

    `runner` 参数只给测试用：真实运行走 `run_shutdown`，测试注入假函数记录 argv，
    保证自动化测试永远不会真的关机。
    """

    def __init__(self, runner=None):
        self._run = runner or run_shutdown
        #: 已排程的目标时刻（也是「是否已排程」的唯一真相）
        self.armed_at: datetime | None = None
        #: 最近一次动作，托盘提示与调试用
        self.last_action: str = ""

    # ---------------- 对外 ----------------
    def cancel(self) -> bool:
        """撤销排程。没有排程时也调一次 `/a`，Windows 只会返回 1116，没有副作用。"""
        had = self.armed_at is not None
        self.armed_at = None
        ok = self._run("/a")
        self.last_action = "cancelled" if had else "noop"
        return ok

    def tick(self, now: datetime, settings: dict) -> dict | None:
        """返回 `{"kind": "notice", "target": datetime, "seconds": int}` 表示刚排了程。

        其余情况一律返回 None —— 调用方不需要知道细节，只负责弹气泡。
        """
        enabled = bool(settings.get("shutdown_enabled", False))
        days = normalize_days(settings.get("shutdown_days"))
        parsed = parse_hhmm(settings.get("shutdown_time", ""))
        try:
            notice_min = int(settings.get("shutdown_notice_min", 1))
        except (TypeError, ValueError):
            notice_min = 1
        notice_min = max(1, min(60, notice_min))

        if not enabled or not days or parsed is None:
            if self.armed_at is not None:
                self.cancel()
            return None

        target = now.replace(hour=parsed[0], minute=parsed[1], second=0, microsecond=0)

        # 改了时间、或跨过午夜 → 旧排程作废，重新算
        if self.armed_at is not None and self.armed_at != target:
            self.cancel()

        if now.weekday() not in days:
            if self.armed_at is not None:
                self.cancel()
            return None

        if now >= target:
            # 已经过点（中途启动 / 休眠唤醒 / 手动撤销过）：今天不补关，等下一次
            self.armed_at = None
            return None

        if self.armed_at is not None:
            return None                     # 已经排过，别重复下命令

        remain = int((target - now).total_seconds())
        if remain > notice_min * 60:
            return None
        if remain < MIN_LEAD_SECONDS:
            return None                     # 只剩十几秒：放弃今天，别突然黑屏

        self.armed_at = target
        ok = self._run("/s", "/t", str(remain))
        self.last_action = "armed" if ok else "failed"
        return {"kind": "notice", "target": target, "seconds": remain} if ok else None

    def describe(self, settings: dict) -> str:
        """一句话状态，给设置页的说明行 / 托盘提示用（不带标题前缀）。"""
        if not bool(settings.get("shutdown_enabled", False)):
            return "未启用"
        days = normalize_days(settings.get("shutdown_days"))
        if not days:
            return "未选择星期，不会关机"
        when = format_hhmm(settings.get("shutdown_time", ""))
        if self.armed_at is not None:
            return f"已排程 · {self.armed_at:%H:%M} 关闭电脑"
        if len(days) == 7:
            names = "每天"
        elif days == [0, 1, 2, 3, 4]:
            names = "周一至周五"
        elif days == [5, 6]:
            names = "周末"
        else:
            names = "、".join(f"周{WEEK_LABELS[d]}" for d in days)
        return f"{names} {when} 关闭电脑"
