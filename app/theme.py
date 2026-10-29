"""设计令牌：色板、字阶、间距、圆角、缓动。

改版背景：原先是「纯黑白灰阶 + 直角平铺」。按 Apple 的视觉体系重做后，
层级靠**明度层次 + 圆角 + 留白**建立，而不是靠描边：

    window  →  surface  →  card  →  card_hover
    #0b0b0d    #131317    #1b1b20   #232329

配色只保留两种语义：
- 主操作 / 强调 = 白色填充（macOS 深色下最「重」的按钮）
- 选中 / 焦点 = 系统蓝 #0a84ff（Apple 深色模式强调色）

字号沿用 Apple 的层级命名（display / title / headline / body / subhead / caption），
尺寸按 4pt 基线缩放。所有像素都过 S()，高分屏不糊。

v1.6.0 起色板可自定义：用户只选 **5 + 4 个锚点色**（界面：背景/卡片/文字/边框/强调；
悬浮条：背景/文字/描边/强调），其余十几个令牌由 ``apply_palette()`` 按「同色系推导」
算出来——Hover/Fill/Track 都是锚点色朝对比方向挪几个百分点，三级文字是文字色向背景色靠。
这样无论用户挑什么组合，层级关系都不会塌（不会出现「卡片比背景还暗」这种事故）。
"""
from __future__ import annotations

import tkinter.font as tkfont

#: 锚点色槽位与出厂配色都在 palette 里定义（那是唯一的真相来源）
from .palette import BAR_SLOTS, DEFAULT_BAR, DEFAULT_UI, UI_SLOTS  # noqa: E402

# ---------- 层级色 ----------
BG = "#0b0b0d"          # 窗口底色
SURFACE = "#131317"     # 区块底
CARD = "#1b1b20"        # 卡片
CARD_HOVER = "#232329"  # 卡片悬停 / 输入框填充
PANEL = SURFACE         # 兼容旧命名
PANEL2 = CARD_HOVER
FILL = "#2a2a31"        # 更实的填充（进度轨道等）

# ---------- 文字 ----------
FG = "#f5f5f7"          # 主文字（Apple 的 near-white）
FG2 = "#a8a8b0"         # 次文字
MUTED = FG2             # 兼容旧命名
FG3 = "#71717a"         # 三级文字
DIM = FG3
LINE = "#2c2c33"        # 分割线 / 描边
TRACK = "#26262c"       # 轨道
SCROLL = "#3d3d45"      # 滚动条滑块（暗态）
SCROLL_HOVER = "#5c5c66"  # 滚动条滑块（悬停 / 拖动）
PILL = "#3a3a42"        # 分段控件选中胶囊

# ---------- 语义色（克制使用） ----------
ACCENT = "#0a84ff"      # 系统蓝：选中、焦点
ACCENT_DIM = "#0a5fbf"
ON_ACCENT = "#ffffff"
WARN = "#ff9f0a"
DANGER = "#ff453a"
OK = "#30d158"

# ---------- 玻璃拟态（顶部悬浮条） ----------
# tkinter 里「真模糊」不可得：`-alpha`（layered 常量透明度）与 `-transparentcolor`
# 互斥，而 DWM 的 accent/acrylic 对 layered 窗口不生效（实测，见 tools/_probe_glass.py）。
# 所以玻璃感 = 整窗 alpha 半透明 + 真圆角 region + 高光/描边/叠层这几样「光学暗示」。
GLASS = "#0a0a0e"        # 玻璃条实色底：整窗 86% 后与壁纸混出半透感
GLASS_DEEP = "#06060a"   # 更暗一档：凹槽 / 内嵌轨道
GLASS_ALPHA = 0.86       # 悬浮条整窗不透明度（默认值，实际值来自设置）
GLASS_RADIUS = 18        # 悬浮条圆角（dp）
GLASS_INSET = 12         # 悬浮条左右留白（dp），让壁纸从两侧透出

# ---------- 悬浮条专用文字 / 线条 ----------
# 悬浮条和设置中心是两套色板：条面压在半透明玻璃上，文字对比度要单独可调。
# 下面这几个派生令牌由 apply_palette() 在文件末尾按出厂配色算一遍，别手改。
BAR_BG = GLASS          # 悬浮条底色（等价于 GLASS，语义更直白）
BAR_FG = FG
BAR_FG2 = FG2
BAR_FG3 = FG3
BAR_LINE = LINE
BAR_ACCENT = ACCENT
BAR_TRACK = GLASS_DEEP
BAR_TICK = "#1f1f24"
BAR_TICK_WEAK = "#17171b"
BAR_EDGE = "#1b1b21"

_S: float = 1.0
_FAMILY = "Segoe UI Variable Text"
_DISPLAY_FAMILY = _FAMILY


def init(root) -> float:
    """初始化 DPI 缩放与字体族，返回缩放系数。"""
    global _S, _FAMILY, _DISPLAY_FAMILY
    try:
        s = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        s = 1.0
    _S = round(s, 3)
    try:
        root.tk.call("tk", "scaling", root.winfo_fpixels("1i") / 72.0)
    except Exception:
        pass

    fams = set(tkfont.families(root))
    for cand in ("Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI",
                 "PingFang SC", "TkDefaultFont"):
        if cand in fams:
            _FAMILY = cand
            break
    for cand in ("Segoe UI Variable Display", "Segoe UI Semibold", _FAMILY):
        if cand in fams:
            _DISPLAY_FAMILY = cand
            break
    return _S


def S(px: float) -> int:
    """逻辑像素 -> 物理像素。"""
    return max(1, int(round(px * _S)))


def P(units: float) -> int:
    """4pt 基线间距：P(2) = 8dp。"""
    return S(units * 4)


def R(px: float) -> int:
    """圆角半径（按 DPI 缩放）。"""
    return S(px)


def F(px: float, bold: bool = False) -> tuple:
    """字号（逻辑像素）-> Tk 字体元组；负值表示像素，避免二次缩放。"""
    return (_DISPLAY_FAMILY if bold else _FAMILY, -S(px), "bold" if bold else "normal")


#: Apple 风格字阶：角色 -> (像素, 是否加粗)
_SCALE = {
    "display": (28, True),
    "title": (20, True),
    "headline": (15, True),
    "body": (13, False),
    "body-bold": (13, True),
    "subhead": (12, False),
    "caption": (11, False),
    "mono": (12, False),
}


def T(role: str) -> tuple:
    px, bold = _SCALE.get(role, (13, False))
    return F(px, bold)


def scale() -> float:
    return _S


def family() -> str:
    return _FAMILY


# ---------------- 颜色工具 ----------------
def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """线性混色：t=0 -> a，t=1 -> b。用于悬停/按下的过渡。"""
    t = max(0.0, min(1.0, t))
    ar, ag, ab = _rgb(a)
    br, bg, bb = _rgb(b)
    return "#{:02x}{:02x}{:02x}".format(
        int(ar + (br - ar) * t), int(ag + (bg - ag) * t), int(ab + (bb - ab) * t))


def lum(color: str) -> float:
    """粗粒度明度（0 黑 ~ 1 白）。只用来判断「深底还是浅底」。"""
    r, g, b = _rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def is_dark(color: str | None = None) -> bool:
    return lum(color if color is not None else BG) < 0.5


def glass(base: str | None = None, amount: float = 0.08) -> str:
    """玻璃叠层：在底色上叠一层「反光」。

    Canvas 没有 RGBA，所有「半透明白/黑」都得先按 alpha 预混成实色，
    再画到半透明窗口上——两层透明叠加后观感与真透明一致。
    叠加方向跟着底色走：深底提亮、浅底压暗，否则浅色主题上所有叠层都会「发白」。
    """
    base = base or GLASS
    target = "#ffffff" if lum(base) < 0.5 else "#000000"
    return mix(base, target, amount)


def glass_dark(base: str | None = None, amount: float = 0.35) -> str:
    """玻璃压暗：用在需要「凹进去」的轨道、槽位上（深浅主题都是往黑走）。"""
    base = base or GLASS
    return mix(base, "#000000", amount)


# ---------------- 缓动 ----------------
def ease_out(t: float) -> float:
    """cubic ease-out：起步快、收尾稳，Apple 动效的默认手感。"""
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# ==================== 外观自定义 ====================
DEFAULT_UI_ALPHA = 1.0
DEFAULT_BAR_ALPHA = GLASS_ALPHA

_UI_ALPHA_MIN, _UI_ALPHA_MAX = 0.75, 1.0
_BAR_ALPHA_MIN, _BAR_ALPHA_MAX = 0.55, 1.0

#: 令牌按用途分「家族」。换肤时要先确定一个旧色**扮演什么角色**，再取该角色
#: 在新配色里的值——不能只按颜色本身查表：
#:
#: 白色在浅色主题里同时可能是「卡片底色」（CARD=#ffffff）和「按钮上的白字」
#: （ON_ACCENT=#ffffff）。两者必须分开，否则按颜色一刀切必然有一半恢复不对
#: （典型症状：切回深色后白卡片还留在深色界面上）。
#:
#: - bg 家族：表面与线条（背景、卡片、填充、描边、轨道……）
#: - fg 家族：文字与强调（主/次/三级文字、强调色、强调色上的前景色）
_UI_SURFACE = ("BG", "SURFACE", "CARD", "CARD_HOVER", "FILL", "PILL", "TRACK",
               "LINE", "SCROLL", "SCROLL_HOVER", "ACCENT", "ACCENT_DIM")
_UI_TEXT = ("FG", "FG2", "FG3", "ACCENT", "ACCENT_DIM", "ON_ACCENT")
#: 悬浮条是**另一套色板**（bar_theme），不能和界面色混在一起查表
_BAR_SURFACE = ("BAR_BG", "GLASS", "BAR_LINE", "BAR_TRACK", "BAR_TICK",
                "BAR_TICK_WEAK", "BAR_EDGE")
_BAR_TEXT = ("BAR_FG", "BAR_FG2", "BAR_FG3", "BAR_ACCENT")

#: 账本里要记录的令牌全集
_UI_TOKENS = ("BG", "SURFACE", "CARD", "CARD_HOVER", "FILL", "PILL", "TRACK",
              "LINE", "SCROLL", "SCROLL_HOVER", "FG", "FG2", "FG3",
              "ACCENT", "ACCENT_DIM", "ON_ACCENT")
_BAR_TOKENS = ("BAR_BG", "GLASS", "BAR_LINE", "BAR_TRACK", "BAR_TICK",
               "BAR_TICK_WEAK", "BAR_EDGE", "BAR_FG", "BAR_FG2", "BAR_FG3", "BAR_ACCENT")

#: 换肤账本：每次 apply_palette 记一份当前配色，remap 靠它把
#: 「旧色 → 旧角色 → 新角色当前值」翻译出来。保留最近几份，
#: 这样连续切换多次也能把任意一轮的旧色还原回去。
_LEDGER: list[dict[str, dict[str, str]]] = []
_LEDGER_MAX = 8


def get(token: str, default: str = "") -> str:
    """取当前配色里某个令牌的值。restyle 时按令牌回填，比按颜色反查更准。"""
    val = globals().get(token)
    return val if isinstance(val, str) else default


def _snapshot() -> dict[str, dict[str, str]]:
    return {
        "ui": {name: globals()[name] for name in _UI_TOKENS},
        "bar": {name: globals()[name] for name in _BAR_TOKENS},
    }


def _role_of(snap: dict[str, str], key: str, tokens) -> str | None:
    """在这个家族里，key 这个颜色扮演的是哪个令牌（取优先级最高的那个）。"""
    for name in tokens:
        val = snap.get(name)
        if isinstance(val, str) and val.lower() == key:
            return name
    return None


def remap(color, kind: str = "bg", family: str = "ui"):
    """把「旧配色里的颜色」翻译成「当前配色里同一角色的颜色」。

    kind="bg" 查表面家族（背景 / 卡片 / 线条），kind="fg" 查文字与强调家族；
    family="ui" 用设置中心色板，"bar" 用悬浮条色板。
    查不到角色就原样返回——字面量颜色（壁纸渐变、开关小圆点）本来就该保持不变。
    """
    if not isinstance(color, str):
        return color
    key = color.strip().lower()
    if not key.startswith("#") or not _LEDGER:
        return color
    if kind == "bg":
        tokens = _BAR_SURFACE if family == "bar" else _UI_SURFACE
    else:
        tokens = _BAR_TEXT if family == "bar" else _UI_TEXT
    cur = _LEDGER[-1][family]
    # 由新到旧找：这个颜色在历史上扮演过什么角色
    for snap in reversed(_LEDGER):
        role = _role_of(snap[family], key, tokens)
        if role:
            return cur.get(role, color)
    return color




def ui_colors() -> dict:
    return {"bg": BG, "card": CARD, "fg": FG, "line": LINE, "accent": ACCENT}


def bar_colors() -> dict:
    return {"bg": GLASS, "fg": BAR_FG, "line": BAR_LINE, "accent": BAR_ACCENT}


def _tone(base: str, amount: float, dark: bool) -> str:
    """朝「远离底色」的方向挪：深色主题提亮、浅色主题压暗。"""
    return mix(base, "#ffffff" if dark else "#000000", amount)


def apply_palette(ui: dict | None = None, bar: dict | None = None) -> tuple[dict, dict]:
    """按用户配色重算全部令牌（模块级常量就地替换），返回生效后的 (ui, bar)。

    调用方负责随后重建悬浮条 / 重着色设置中心——本函数只改颜色，不动任何窗口。
    """
    global BG, SURFACE, CARD, CARD_HOVER, FILL, PANEL, PANEL2
    global FG, FG2, FG3, MUTED, DIM, LINE, TRACK, SCROLL, SCROLL_HOVER, PILL
    global ACCENT, ACCENT_DIM, ON_ACCENT
    global GLASS, GLASS_DEEP, BAR_BG, BAR_FG, BAR_FG2, BAR_FG3, BAR_LINE, BAR_ACCENT
    global BAR_TRACK, BAR_TICK, BAR_TICK_WEAK, BAR_EDGE

    ui = {**DEFAULT_UI, **(ui or {})}
    bar = {**DEFAULT_BAR, **(bar or {})}

    # ---- 设置中心 ----
    # 层级差全部按「锚点色朝对比方向挪几个百分点」推导，系数就是拿 1.5.0 的
    # 手调色板反解出来的：深色下 SURFACE 3.3%、CARD_HOVER 3.6%、FILL 6.8%…
    # 浅色主题同样的百分比看不出层次（白卡在黑字面前太亮），所以放大 1.7 倍。
    dark = lum(ui["bg"]) < 0.5
    k = 1.0 if dark else 1.7
    BG, CARD, LINE = ui["bg"], ui["card"], ui["line"]
    FG, ACCENT = ui["fg"], ui["accent"]
    SURFACE = _tone(BG, 0.033 * k, dark)
    CARD_HOVER = _tone(CARD, 0.036 * k, dark)
    FILL = _tone(CARD, 0.068 * k, dark)
    TRACK = _tone(BG, 0.110 * k, dark)
    PILL = _tone(CARD, 0.135 * k, dark)
    FG2 = mix(FG, BG, 0.33)            # 次文字：向背景靠 33%
    FG3 = mix(FG, BG, 0.56)            # 三级文字
    SCROLL = mix(LINE, FG, 0.085)
    SCROLL_HOVER = mix(LINE, FG, 0.24)
    ACCENT_DIM = mix(ACCENT, "#000000", 0.28)
    ON_ACCENT = "#ffffff" if lum(ACCENT) < 0.62 else "#0b0b0d"
    PANEL, PANEL2, MUTED, DIM = SURFACE, CARD_HOVER, FG2, FG3

    # ---- 悬浮条 ----
    bar_dark = lum(bar["bg"]) < 0.5
    GLASS, BAR_FG, BAR_LINE, BAR_ACCENT = bar["bg"], bar["fg"], bar["line"], bar["accent"]
    BAR_BG = GLASS
    GLASS_DEEP = mix(GLASS, "#000000", 0.30)
    BAR_FG2 = mix(BAR_FG, GLASS, 0.34)
    BAR_FG3 = mix(BAR_FG, GLASS, 0.56)
    # 轨道永远是「凹」：深色条压得更黑，浅色条只压一点点
    BAR_TRACK = mix(GLASS, "#000000", 0.45 if bar_dark else 0.10)
    BAR_TICK = mix(GLASS, BAR_LINE, 0.73)        # 6 点整点网格
    BAR_TICK_WEAK = mix(GLASS, BAR_LINE, 0.53)   # 其余整点
    BAR_EDGE = mix(GLASS, BAR_LINE, 0.55)        # 下沿内阴影，带一点描边色

    # ---- 记进换肤账本 ----
    # remap() 靠它把「旧色扮演的角色」翻译成「新配色里该角色的当前值」。
    # 账本保留最近几份，连续切换多次也能把任意一轮的旧色还原回去。
    _LEDGER.append(_snapshot())
    if len(_LEDGER) > _LEDGER_MAX:
        del _LEDGER[0]
    return dict(ui), dict(bar)


def clamp_alpha(value, default: float, lo: float, hi: float) -> float:
    try:
        return round(max(lo, min(hi, float(value))), 2)
    except (TypeError, ValueError):
        return default


# 出厂配色跑一遍推导：让 BAR_TICK / BAR_EDGE 这些派生令牌在任何导入路径下
# 都与 apply_palette() 的结果一致（此时账本里只有这一份）。
apply_palette(DEFAULT_UI, DEFAULT_BAR)
