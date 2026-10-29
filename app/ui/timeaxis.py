"""今日时间轴：把 00:00–24:00 映射成横向像素，并压缩没有作息数据的空白时段。

为什么需要
----------
等距的 24 小时轴上，凌晨 0–6 点这类「没课」的空白会白占掉整条宽度的 1/4；
真正有课的 09:50–22:20 被压在后半段，一节课只剩五十来像素，课程名写不下，
30 分钟的晚自习更会糊成一个没有字的白点。压缩空白就是把这些地方还给活跃时段。

压缩规则（全部阈值都在本文件头部，改动请同步 README「时间轴压缩」一节）
--------------------------------------------------------------------
1. **活跃窗口** = `[首个时段开始 − PAD, 末个时段结束 + PAD]`，PAD = 10 分钟。
   判断只看「今天有没有这一段作息」，不看星期、不看课程名。
2. **窗口内部 1:1** —— 45 分钟的课就是 45 分钟的长度，绝不缩放，
   「时长即长度」这条不能破，否则作息条就没有可读性了。
3. **窗口内部的大空档**（午休、晚饭之类）：前 `GAP_KEEP`(45 分钟) 保留原比例，
   超出的部分按 `GAP_RATE`(0.35) 折算。45 分钟以内的空档完全不动，
   免得课间与相邻课块在视觉上粘成一团、看不出边界。
4. **窗口之外**（00:00→窗口左沿、窗口右沿→24:00）压成固定像素：
   整宽的 `EDGE_RATIO`(4.5%)，并夹在 `EDGE_MIN`(22dp) ~ `EDGE_MAX`(90dp) 之间。
   6 小时的凌晨因此只占几十像素。
5. 被折算过的区段记进 `compressed`，由调用方画暗底 / 斜纹，
   让「这一段不是等比例」这件事**看得见**，不至于误导成时间失真。
6. **全天没有任何时段 → 完全等距**。没有数据时不该替用户假设哪里活跃。

对外只有三件事：`to_x(秒)`、`to_t(像素)`、`hour_ticks(最小间距)`。
"""
from __future__ import annotations

import bisect

from .. import theme

DAY = 86400.0

#: 活跃窗口前后各留的呼吸位（秒）
PAD = 600
#: 窗口内部空档保留原比例的时长（秒），超出部分才折算
GAP_KEEP = 45 * 60
#: 超出部分折算到原长的多少
GAP_RATE = 0.35
#: 窗口之外压成整条宽度的多少
EDGE_RATIO = 0.045
#: 上一条的像素上下限（dp）
EDGE_MIN = 22
EDGE_MAX = 90


def _eff_gap(seconds: float) -> float:
    """空档折算成「等效秒」：短空档原样保留，长空档压缩超出部分。"""
    if seconds <= GAP_KEEP:
        return seconds
    return GAP_KEEP + (seconds - GAP_KEEP) * GAP_RATE


class TimeAxis:
    """一段单调递增的「秒 → 像素」分段线性映射。"""

    def __init__(self, slots, x0: float, x1: float):
        self.x0 = float(x0)
        self.x1 = max(float(x1), self.x0 + 1.0)
        #: 被压缩（非等比例）的时间区段，按时间升序，供绘制方画暗底/斜纹
        self.compressed: list[tuple[float, float]] = []
        #: 活跃窗口（无数据时就是全天）
        self.active: tuple[float, float] = (0.0, DAY)
        self._ts = [0.0, DAY]
        self._xs = [self.x0, self.x1]
        self._build(slots)

    # ---------------- 构建 ----------------
    def _build(self, slots) -> None:
        spans = sorted(
            (max(0.0, float(s.start_s)), min(DAY, float(s.end_s)))
            for s in (slots or [])
            if s.end_s > s.start_s
        )
        if not spans:
            return                       # 全天无时段：保持等距

        lo = max(0.0, spans[0][0] - PAD)
        hi = min(DAY, spans[-1][1] + PAD)
        if hi - lo < 60:
            return

        # 窗口内部切成「实段（1:1）」与「空档（折算）」交替的序列
        segs: list[tuple[float, float, float]] = []
        cursor = lo
        for start, end in spans:
            start = max(start, cursor)
            end = min(end, hi)
            if end <= start:
                continue                 # 被前一段完全覆盖（数据重叠）
            if start > cursor:
                segs.append((cursor, start, _eff_gap(start - cursor)))
            segs.append((start, end, end - start))
            cursor = end
        if cursor < hi:
            segs.append((cursor, hi, _eff_gap(hi - cursor)))

        total = sum(eff for _, _, eff in segs)
        if total <= 0:
            return

        width = self.x1 - self.x0
        edge = min(max(width * EDGE_RATIO, float(theme.S(EDGE_MIN))), float(theme.S(EDGE_MAX)))
        edge_l = edge if lo > 0 else 0.0
        edge_r = edge if hi < DAY else 0.0
        # 两侧都压缩时不许吃掉半条以上，否则中间没地方放
        if edge_l + edge_r > width * 0.5:
            edge_l = min(edge_l, width * 0.25)
            edge_r = min(edge_r, width * 0.25)
        avail = max(1.0, width - edge_l - edge_r)

        knots: list[tuple[float, float]] = []
        if lo > 0:
            knots.append((0.0, self.x0))
            self.compressed.append((0.0, lo))          # 头部空白
        x = self.x0 + edge_l
        knots.append((lo, x))
        for t0, t1, eff in segs:
            x += avail * eff / total
            knots.append((t1, x))
            if eff < (t1 - t0) - 0.5:                  # 确实被折算过
                self.compressed.append((t0, t1))
        if hi < DAY:
            knots.append((DAY, self.x1))
            self.compressed.append((hi, DAY))          # 尾部空白

        # 端点必须精确贴住画布两侧，否则最右的块会差一两像素
        knots[0] = (knots[0][0], self.x0)
        knots[-1] = (knots[-1][0], self.x1)

        ts, xs = [knots[0][0]], [knots[0][1]]
        for t, xx in knots[1:]:
            if t <= ts[-1] + 1e-9:                     # 同一时刻只留一个节点
                xs[-1] = xx
            else:
                ts.append(t)
                xs.append(xx)
        self._ts, self._xs = ts, xs
        self.active = (lo, hi)

    # ---------------- 查询 ----------------
    def to_x(self, seconds: float) -> float:
        """当天秒数 → 横向像素。结果单调，to_x(0)=左端、to_x(86400)=右端。"""
        t = min(DAY, max(0.0, float(seconds)))
        i = bisect.bisect_right(self._ts, t) - 1
        i = max(0, min(i, len(self._ts) - 2))
        t0, t1 = self._ts[i], self._ts[i + 1]
        x0, x1 = self._xs[i], self._xs[i + 1]
        if t1 - t0 < 1e-9:
            return x1
        return x0 + (x1 - x0) * (t - t0) / (t1 - t0)

    def to_t(self, x: float) -> float:
        """横向像素 → 当天秒数（反向查询，探针与测试用）。"""
        px = min(self.x1, max(self.x0, float(x)))
        i = bisect.bisect_right(self._xs, px) - 1
        i = max(0, min(i, len(self._xs) - 2))
        x0, x1 = self._xs[i], self._xs[i + 1]
        if x1 - x0 < 1e-9:
            return self._ts[i + 1]
        return self._ts[i] + (self._ts[i + 1] - self._ts[i]) * (px - x0) / (x1 - x0)

    def hour_ticks(self, min_px: float) -> list[tuple[int, float]]:
        """整点刻度 [(时, 像素)]，压缩区里挤不下的自动跳过。

        0 点与 24 点尽量保留——它们是这条轴的两端；中间与末端撞上时，
        宁可丢掉中间那个，也不让轴尾没有落款。
        """
        out: list[tuple[int, float]] = []
        for hour in range(25):
            x = self.to_x(hour * 3600)
            if out and x - out[-1][1] < min_px:
                if hour == 24 and len(out) > 1:
                    out.pop()
                else:
                    continue
            out.append((hour, x))
        return out
