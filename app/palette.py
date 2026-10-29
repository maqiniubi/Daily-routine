"""外观配色的数据层：预设方案、颜色校验、落地到 theme / ttk。

这一层只做「数据」，不碰任何窗口：
- ``DEFAULT_UI`` / ``DEFAULT_BAR`` 是全应用唯一的出厂配色来源（theme.py 也从这里取）；
- ``PRESETS`` 是几套成对的方案，一键切换不会出现「界面浅色、悬浮条深色」的违和组合；
- ``apply()`` 把配色写进 theme 的模块级令牌并重刷 ttk 样式，由控制器负责后续重建窗口。

配色用「锚点色」模型：用户只挑 5 + 4 个颜色，其余派生色由 theme.apply_palette 推导，
所以不存在「用户把卡片色设得比背景还暗」这类把界面搞崩的可能。
"""
from __future__ import annotations

import re

#: 设置中心（普通窗口）可调的锚点色
UI_SLOTS = ("bg", "card", "fg", "line", "accent")
#: 顶部悬浮条可调的锚点色
BAR_SLOTS = ("bg", "fg", "line", "accent")

#: 出厂配色 = v1.5.0 的 Apple 深色方案
DEFAULT_UI = {"bg": "#0b0b0d", "card": "#1b1b20", "fg": "#f5f5f7",
              "line": "#2c2c33", "accent": "#0a84ff"}
DEFAULT_BAR = {"bg": "#0a0a0e", "fg": "#f5f5f7", "line": "#2c2c33", "accent": "#0a84ff"}

DEFAULT_UI_ALPHA = 1.0
DEFAULT_BAR_ALPHA = 0.86

#: 预设方案：键、显示名、界面配色、悬浮条配色、两个不透明度
PRESETS: list[dict] = [
    {
        "key": "dark", "name": "深色（默认）",
        "ui": dict(DEFAULT_UI), "bar": dict(DEFAULT_BAR),
        "ui_alpha": 1.0, "bar_alpha": 0.86,
    },
    {
        "key": "light", "name": "浅色",
        "ui": {"bg": "#eceef2", "card": "#ffffff", "fg": "#1c1c1e",
               "line": "#d6d9e0", "accent": "#0a84ff"},
        "bar": {"bg": "#f7f8fa", "fg": "#1c1c1e", "line": "#d6d9e0", "accent": "#0a84ff"},
        "ui_alpha": 1.0, "bar_alpha": 0.92,
    },
    {
        "key": "midnight", "name": "午夜蓝",
        "ui": {"bg": "#0a1020", "card": "#141c2f", "fg": "#e8eef8",
               "line": "#26314a", "accent": "#4b9bff"},
        "bar": {"bg": "#070c18", "fg": "#e8eef8", "line": "#26314a", "accent": "#4b9bff"},
        "ui_alpha": 1.0, "bar_alpha": 0.86,
    },
    {
        "key": "forest", "name": "松林绿",
        "ui": {"bg": "#0b1310", "card": "#16211b", "fg": "#e9f3ed",
               "line": "#28362e", "accent": "#30d158"},
        "bar": {"bg": "#070f0c", "fg": "#e9f3ed", "line": "#28362e", "accent": "#30d158"},
        "ui_alpha": 1.0, "bar_alpha": 0.86,
    },
    {
        "key": "sand", "name": "暖砂",
        "ui": {"bg": "#191310", "card": "#241c17", "fg": "#f7ede2",
               "line": "#3a2f27", "accent": "#ff9f0a"},
        "bar": {"bg": "#140f0c", "fg": "#f7ede2", "line": "#3a2f27", "accent": "#ff9f0a"},
        "ui_alpha": 1.0, "bar_alpha": 0.88,
    },
    {
        "key": "oled", "name": "纯黑",
        "ui": {"bg": "#000000", "card": "#0d0d10", "fg": "#ffffff",
               "line": "#232327", "accent": "#0a84ff"},
        "bar": {"bg": "#000000", "fg": "#ffffff", "line": "#232327", "accent": "#0a84ff"},
        "ui_alpha": 1.0, "bar_alpha": 0.82,
    },
]

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def normalize(color) -> str | None:
    """把用户输入/手改 JSON 的颜色规范成 '#rrggbb'；认不出来返回 None。"""
    if not isinstance(color, str):
        return None
    m = _HEX_RE.match(color.strip())
    if not m:
        return None
    body = m.group(1).lower()
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    return f"#{body}"


def normalize_theme(raw, slots=UI_SLOTS, defaults=None) -> dict:
    """补全缺失槽位、丢弃非法值；整块缺失就整体回落到默认。"""
    out = dict(defaults or DEFAULT_UI)
    if isinstance(raw, dict):
        for key in slots:
            fixed = normalize(raw.get(key))
            if fixed:
                out[key] = fixed
    return out


def preset(key: str) -> dict | None:
    for item in PRESETS:
        if item["key"] == key:
            return item
    return None


def match_preset(ui: dict, bar: dict) -> dict | None:
    """当前配色正好等于某套预设时返回它（用于高亮预设按钮）。"""
    for item in PRESETS:
        if all(normalize(item["ui"].get(k)) == normalize(ui.get(k)) for k in UI_SLOTS) and \
           all(normalize(item["bar"].get(k)) == normalize(bar.get(k)) for k in BAR_SLOTS):
            return item
    return None


def alphas(settings: dict) -> tuple[float, float]:
    """(界面不透明度, 悬浮条不透明度)，都已夹到合法区间。"""
    from .theme import clamp_alpha

    ui = clamp_alpha(settings.get("ui_alpha"), DEFAULT_UI_ALPHA, 0.75, 1.0)
    bar = clamp_alpha(settings.get("bar_alpha"), DEFAULT_BAR_ALPHA, 0.55, 1.0)
    return ui, bar


def apply(settings: dict, root=None, ttk: bool = True,
          groups: tuple[str, ...] = ("form", "table")) -> tuple[dict, dict]:
    """把设置里的配色写进 theme（并重刷 ttk 样式），返回生效后的 (ui, bar)。

    ttk=False 只换 theme 令牌、不动 ttk 样式：拖动透明度这类连续操作用它做
    「即时反馈」——ttk 样式重建要几十毫秒，不能每一步都做。

    groups 传给 init_style：换配色时一般只刷 "form"，表格样式（"table"）
    等切到表格页再刷（Treeview 重新派生要二十多毫秒）。
    """
    from . import theme

    ui = normalize_theme(settings.get("ui_theme"), UI_SLOTS, DEFAULT_UI)
    bar = normalize_theme(settings.get("bar_theme"), BAR_SLOTS, DEFAULT_BAR)
    theme.apply_palette(ui, bar)
    if root is not None and ttk:
        try:
            from .ui.common import init_style

            init_style(root, groups)     # ttk 的 Treeview / Entry / Spinbox 是样式驱动的
        except Exception:
            pass
    return ui, bar


def restore_defaults(settings: dict) -> None:
    """只把外观恢复出厂，不动作息表 / 课程 / 倒计时。"""
    settings["ui_theme"] = dict(DEFAULT_UI)
    settings["bar_theme"] = dict(DEFAULT_BAR)
    settings["ui_alpha"] = DEFAULT_UI_ALPHA
    settings["bar_alpha"] = DEFAULT_BAR_ALPHA
