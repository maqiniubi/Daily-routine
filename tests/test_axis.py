"""时间轴压缩规则测试（无界面）：只验 `app/ui/timeaxis.py` 的映射，不碰 Tk。

覆盖的规则：
1. 端点精确、映射单调（数据准确性的底线）；
2. 活跃窗口内 1:1（时长即长度，不许缩放）；
3. 窗口外空白压成固定像素（凌晨不再白占四分之一条）；
4. 窗口内大空档按 GAP_KEEP / GAP_RATE 折算，短空档不动；
5. 无数据 / 全天有课时退化为等距；
6. 刻度降采样后仍保两端。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_axis_test_")

from app.ui.timeaxis import DAY, GAP_KEEP, GAP_RATE, TimeAxis  # noqa: E402

X0, X1 = 1.0, 1823.0
W = X1 - X0
PASS = 0


def check(cond: bool, label: str) -> None:
    global PASS
    if not cond:
        raise AssertionError(f"FAIL: {label}")
    PASS += 1
    print(f"  ok  {label}")


class Slot:
    """只带 start_s / end_s 的假时段，够 TimeAxis 用。"""

    def __init__(self, start: str, end: str, name: str = ""):
        self.start_s = _sec(start)
        self.end_s = _sec(end)
        self.name = name


def _sec(hhmm: str) -> int:
    h, m = hhmm.split(":")[:2]
    return int(h) * 3600 + int(m) * 60


def _blank() -> TimeAxis:
    """一节课都没有：应该完全等距。"""
    return TimeAxis([], X0, X1)


def test_empty() -> None:
    print("[空数据：等距]")
    ax = _blank()
    check(abs(ax.to_x(0) - X0) < 0.01, "无数据 to_x(00:00) = 左端")
    check(abs(ax.to_x(43200) - (X0 + W / 2)) < 0.6, "无数据 12:00 落在正中间")
    check(abs(ax.to_x(DAY) - X1) < 0.01, "无数据 to_x(24:00) = 右端")
    check(not ax.compressed, "无数据没有任何压缩区段")


def test_endpoints_and_monotonic() -> None:
    print("[端点与单调性]")
    ax = TimeAxis([Slot("09:50", "10:35"), Slot("21:50", "22:20")], X0, X1)
    check(abs(ax.to_x(0) - X0) < 0.01, "to_x(00:00) 精确贴住左端")
    check(abs(ax.to_x(DAY) - X1) < 0.01, "to_x(24:00) 精确贴住右端")
    prev = -1.0
    worst = 0.0
    t = 0
    while t <= DAY:
        x = ax.to_x(t)
        worst = max(worst, prev - x)          # 允许的倒退量
        prev = x
        t += 300
    check(worst <= 1e-6, f"5 分钟步长采样整条轴单调不减（最大倒退 {worst:.6f}px）")


def test_active_window_ratio() -> None:
    print("[活跃窗口 1:1]")
    # 45 分钟 x2 + 30 分钟 x1，都在活跃窗口内
    ax = TimeAxis([Slot("09:00", "09:45"), Slot("10:00", "10:45"), Slot("21:50", "22:20")],
                  X0, X1)
    a = ax.to_x(9 * 3600 + 45 * 60) - ax.to_x(9 * 3600)
    b = ax.to_x(10 * 3600 + 45 * 60) - ax.to_x(10 * 3600)
    c = ax.to_x(22 * 3600 + 20 * 60) - ax.to_x(21 * 3600 + 50 * 60)
    check(abs(a - b) < 0.6, f"两节均为 45 分钟 → 宽度相同（{a:.1f} / {b:.1f}px）")
    check(abs(a / c - 1.5) < 0.03, f"45 分钟 : 30 分钟 = 1.5（实测 {a / c:.3f}）")
    # 同一段内任取两点，比例与真实秒数一致
    p1 = ax.to_x(11 * 3600) - ax.to_x(10 * 3600 + 45 * 60)
    check(p1 > 0, f"10:45→11:00 有正宽度（{p1:.1f}px）")


def test_edge_compression() -> None:
    print("[凌晨 / 深夜压缩]")
    ax = TimeAxis([Slot("09:50", "10:35"), Slot("21:50", "22:20")], X0, X1)
    head = ax.to_x(9 * 3600) - ax.to_x(0)
    tail = ax.to_x(DAY) - ax.to_x(22 * 3600 + 30 * 60)
    check(head < W * 0.10, f"00:00–09:00 压到全宽 {head / W * 100:.1f}%（< 10%）")
    check(tail < W * 0.10, f"22:30–24:00 压到全宽 {tail / W * 100:.1f}%（< 10%）")
    active = ax.to_x(22 * 3600 + 20 * 60) - ax.to_x(9 * 3600 + 50 * 60)
    check(active > W * 0.78, f"活跃时段（09:50–22:20）占全宽 {active / W * 100:.1f}%（> 78%）")
    spans = [(round(a), round(b)) for a, b in ax.compressed]
    check(any(a == 0 and b >= 9 * 3600 for a, b in spans),
          f"凌晨整段被记为压缩区 {spans[:1]}")
    check(any(a >= 22 * 3600 and b == int(DAY) for a, b in spans), "深夜整段被记为压缩区")


def test_inner_gap() -> None:
    print("[窗口内的大空档]")
    # 09:00-10:00 与 14:00-15:00：中间 4 小时午休
    ax = TimeAxis([Slot("09:00", "10:00"), Slot("14:00", "15:00")], X0, X1)
    minute_w = (ax.to_x(10 * 3600) - ax.to_x(9 * 3600)) / 60.0   # 1 分钟的真实像素
    gap_px = ax.to_x(14 * 3600) - ax.to_x(10 * 3600)
    gap_min = gap_px / minute_w
    want = GAP_KEEP / 60 + (240 - GAP_KEEP / 60) * GAP_RATE      # 45 + 195*0.35 = 113.25
    check(abs(gap_min - want) < 3, f"4 小时午休折算成 {gap_min:.1f} 分钟（期望 {want:.2f}）")
    check(gap_min < 240 * 0.6, f"确实压缩了（{gap_min / 240 * 100:.0f}% 原文）")


def test_short_gap_kept() -> None:
    print("[短空档不压缩]")
    # 10 分钟课间 < GAP_KEEP，应保持 1:1
    ax = TimeAxis([Slot("09:00", "09:45"), Slot("09:55", "10:40")], X0, X1)
    w45 = ax.to_x(9 * 3600 + 45 * 60) - ax.to_x(9 * 3600)
    gap = ax.to_x(9 * 3600 + 55 * 60) - ax.to_x(9 * 3600 + 45 * 60)
    check(abs(gap / w45 - 10 / 45) < 0.04, f"10 分钟课间 = 45 分钟的 2/9（实测 {gap / w45:.3f}）")
    inner = [s for s in ax.compressed if s[0] >= 9 * 3600 and s[1] <= 11 * 3600]
    check(not inner, "短课间不进入压缩区")


def test_full_day_is_linear() -> None:
    print("[全天排满：不压缩]")
    ax = TimeAxis([Slot("00:00", "12:00"), Slot("12:00", "24:00")], X0, X1)
    check(not ax.compressed, "从 00:00 排到 24:00 时无压缩区段")
    mid = ax.to_x(43200)
    check(abs(mid - (X0 + W / 2)) < 0.6, f"12:00 仍在中间（{mid:.1f}px）")


def test_inverse() -> None:
    print("[反查 to_t]")
    ax = TimeAxis([Slot("09:50", "10:35"), Slot("21:50", "22:20")], X0, X1)
    worst = 0.0
    for h in (0, 3, 7, 9, 12, 18, 22, 23):
        t = h * 3600
        worst = max(worst, abs(ax.to_t(ax.to_x(t)) - t))
    check(worst < 2, f"to_t(to_x(t)) 往返误差 < 2 秒（最大 {worst:.3f}s）")


def test_ticks() -> None:
    print("[刻度降采样]")
    ax = TimeAxis([Slot("09:50", "10:35"), Slot("21:50", "22:20")], X0, X1)
    ticks = ax.hour_ticks(54)
    check(len(ticks) >= 10, f"活跃区仍有足够刻度（{len(ticks)} 个）")
    gaps = [b[1] - a[1] for a, b in zip(ticks, ticks[1:])]
    check(min(gaps) >= 54, f"相邻刻度间距 ≥ 54px（最小 {min(gaps):.1f}）")
    check(ticks[0][0] == 0, "0 点刻度保留（轴头）")
    check(ticks[-1][0] == 24, "24 点刻度保留（轴尾）")


def test_overlap_and_unsorted() -> None:
    print("[乱序 / 重叠数据]")
    ax = TimeAxis([Slot("21:50", "22:20"), Slot("09:00", "10:00"), Slot("09:30", "09:50")],
                  X0, X1)
    check(abs(ax.to_x(0) - X0) < 0.01 and abs(ax.to_x(DAY) - X1) < 0.01, "乱序输入下端点仍精确")
    check(ax.to_x(10 * 3600) > ax.to_x(9 * 3600), "重叠时段不产生零宽或倒退")


if __name__ == "__main__":
    test_empty()
    test_endpoints_and_monotonic()
    test_active_window_ratio()
    test_edge_compression()
    test_inner_gap()
    test_short_gap_kept()
    test_full_day_is_linear()
    test_inverse()
    test_ticks()
    test_overlap_and_unsorted()
    print(f"\nALL PASSED ({PASS} checks)")
