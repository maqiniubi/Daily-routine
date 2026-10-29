"""赞赏支持面板：微信 / 支付宝收款码。

图片在构建期已转成 PNG（Tk 原生只认 PNG/GIF），运行期不需要 Pillow。
改版：两张收款码放进圆角卡片，银行卡式的等宽排布，标题与说明按字阶分层。
"""
from __future__ import annotations

import tkinter as tk

from .. import config, theme, win32util
from .common import center
from .widgets import RoundedBox


class SponsorWindow(tk.Toplevel):
    def __init__(self, parent, ctl=None):
        super().__init__(parent)
        self.withdraw()
        self.title("赞赏支持 · 班级作息助手")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.ctl = ctl
        self._images: list[tk.PhotoImage] = []
        body = tk.Frame(self, bg=theme.BG, padx=theme.P(7), pady=theme.P(5))
        body.pack(fill="both", expand=True)

        tk.Label(body, text="赞赏支持", bg=theme.BG, fg=theme.FG, font=theme.T("display"),
                 anchor="w").pack(fill="x")
        tk.Label(body, text="如果这个小工具帮你省下了时间，欢迎扫码支持一下。",
                 bg=theme.BG, fg=theme.FG2, font=theme.T("body"), anchor="w",
                 justify="left", wraplength=theme.S(520)).pack(fill="x", pady=(theme.S(4), theme.P(5)))

        cards = tk.Frame(body, bg=theme.BG)
        cards.pack(fill="x")
        self._card(cards, "微信赞赏", "sponsor_wechat.png", "微信扫一扫").pack(
            side="left", padx=(0, theme.P(3)))
        self._card(cards, "支付宝", "sponsor_alipay.png", "支付宝扫一扫").pack(side="left")

        tk.Label(body, text="赞赏完全自愿，不影响任何功能使用 · 感谢每一位支持者",
                 bg=theme.BG, fg=theme.FG3, font=theme.T("caption"), anchor="w").pack(
            fill="x", pady=(theme.P(4), 0))

        self.update_idletasks()
        center(self, parent if parent and parent.winfo_viewable() else None,
               width=body.winfo_reqwidth() + theme.S(8),
               height=body.winfo_reqheight() + theme.S(8))
        self.transient(parent)
        self.deiconify()
        self.attributes("-topmost", True)
        self.lift()
        win32util.set_dark_titlebar(win32util.hwnd_of(self))
        self.after(80, self.focus_force)
        self.bind("<Escape>", lambda e: self.destroy())

    def _card(self, parent, title: str, filename: str, caption: str) -> tk.Frame:
        box = RoundedBox(parent, radius=16, fill=theme.CARD, pad=0)
        card = tk.Frame(box.body, bg=theme.CARD, padx=theme.P(3), pady=theme.P(3))
        card.pack(fill="both", expand=True)

        tk.Label(card, text=title, bg=theme.CARD, fg=theme.FG, font=theme.T("headline"),
                 anchor="w").pack(fill="x")
        tk.Label(card, text=caption, bg=theme.CARD, fg=theme.FG3, font=theme.T("caption"),
                 anchor="w").pack(fill="x", pady=(theme.S(1), theme.P(2)))

        holder = tk.Frame(card, bg="#ffffff", padx=theme.S(8), pady=theme.S(8))
        holder.pack()
        path = config.resource_path("assets", filename)
        try:
            img = tk.PhotoImage(file=str(path))
            # 320px 原图按 216dp 显示（高 DPI 下清晰度足够）
            factor = max(1, round(img.width() / max(1, theme.S(216))))
            if factor > 1:
                img = img.subsample(factor, factor)
            self._images.append(img)
            tk.Label(holder, image=img, bg="#ffffff", bd=0).pack()
        except Exception:
            tk.Label(holder, text="二维码加载失败", bg="#ffffff", fg="#111111",
                     font=theme.T("caption"), width=20, height=8).pack()
        card.update_idletasks()
        box.fit()          # 尺寸含圆角内缩，不能直接用 card.winfo_reqwidth()
        return box

def show_sponsor(parent, ctl=None) -> "SponsorWindow":
    return SponsorWindow(parent, ctl)
