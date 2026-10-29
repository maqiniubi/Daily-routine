"""应用控制器：串起数据、悬浮条、提醒与设置中心。"""
from __future__ import annotations

import os
import threading

import tkinter as tk
from datetime import datetime

from . import config, palette
from .models import AppData, default_data
from .power import ShutdownScheduler
from .scheduler import ReminderEngine
from .store import Store
from .tray import TrayIcon
from .ui.desktop_countdown import DesktopCountdown
from .ui.main_window import MainWindow
from .ui.toast import ToastManager
from .ui.topbar import TopBar


class Controller:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.store = Store()
        self.data: AppData = self.store.load()
        # 先把用户配色铺到 theme 上：后面创建的一切（悬浮条、气泡、菜单）都按它上色
        palette.apply(self.data.settings, root)
        self.toast = ToastManager(root, lambda: self.topbar.height())
        self.reminder = ReminderEngine(self.data, self._on_remind)
        # 定时关机：必须在 TopBar 之前建好，因为第一秒的 tick 就会问它要不要排程
        self.shutdown = ShutdownScheduler()
        self.topbar = TopBar(root, self)
        # 弹窗（消息框 / 表单）要按实时条高避让，而 common 里拿不到控制器，
        # 所以把控制器挂在根窗口身上，由 common.bar_bottom() 反查。
        try:
            root._ctl = self
        except Exception:
            pass
        self.main_window: MainWindow | None = None
        self.desktop_countdown: DesktopCountdown | None = None
        self.tray: TrayIcon | None = None
        self._tray_tip_job = None
        self._setup_tray()
        self.sync_desktop_countdown()
        self.apply_click_through()

    # ---------------- 外观 ----------------
    def apply_appearance(self) -> None:
        """外观页改完配色：先下发到 theme / ttk，再让悬浮条与设置中心就地换装。

        顺序不能反：theme 令牌必须先更新，否则重画出来的还是旧色。

        悬浮条走 restyle()（只换色，不重建控件）——换配色不改结构，
        没必要把每个控件 destroy 掉重来一遍（那是 100 多毫秒的代价）。
        """
        palette.apply(self.data.settings, self.root, groups=("form",))
        try:
            self.topbar.restyle()          # 悬浮条就地换色（alpha、圆角、几何一起重申）
        except Exception:
            pass
        try:
            self.toast.clear()             # 旧气泡是按旧配色画的，留着就是两块色差
        except Exception:
            pass
        try:
            self.sync_desktop_countdown()  # 贴纸按新色重建
        except Exception:
            pass
        mw = self.main_window
        if mw is not None and mw.winfo_exists():
            try:
                mw.restyle()
            except Exception:
                pass

    # ---------------- 鼠标穿透 ----------------
    def apply_click_through(self) -> None:
        """开关鼠标穿透：悬浮条 / 提醒气泡 / 桌面贴纸全部让位给下层窗口。

        只有设置中心（以及它弹出的表单、赞赏面板）保留正常交互——
        设置中心是唯一能「改回来」的地方，赞赏面板需要点链接。
        """
        on = bool(self.data.settings.get("click_through", True))
        try:
            self.topbar.set_click_through(on)
        except Exception:
            pass
        try:
            self.toast.set_click_through(on)
        except Exception:
            pass
        if self.desktop_countdown is not None and self.desktop_countdown.winfo_exists():
            try:
                self.desktop_countdown.set_click_through(on)
            except Exception:
                pass

    # ---------------- 托盘 ----------------
    def _setup_tray(self) -> None:
        items = [
            ("打开设置中心", self.open_settings),
            ("重新校准并置顶", self._recalibrate),
            ("显示 / 隐藏桌面倒计时", self.toggle_desktop_countdown),
            ("切换鼠标穿透（设置中心可改）", self.toggle_click_through),
            ("取消定时关机", self.cancel_shutdown),
            ("赞赏支持", self.show_sponsor),
            None,
            ("退出程序（唯一关闭途径）", self.quit_app),
        ]
        self.tray = TrayIcon(self.root, f"{config.APP_TITLE} · 永恒　右键查看菜单",
                             config.resource_path("assets", "icon.ico"), items)
        self.tray.show()
        self._refresh_tray_tip()

    def _recalibrate(self) -> None:
        self.topbar.recalibrate()

    def _refresh_tray_tip(self) -> None:
        """托盘悬停提示带上当前状态，鼠标停上去就能看到进度。"""
        try:
            if self.tray is not None:
                head = self.topbar.lbl_state.cget("text") or "常驻中"
                self.tray.set_tooltip(f"{config.APP_TITLE}\n{head}　{datetime.now():%H:%M}")
        except Exception:
            pass
        try:
            self._tray_tip_job = self.root.after(15000, self._refresh_tray_tip)
        except Exception:
            pass

    def toggle_click_through(self) -> None:
        """托盘侧的快捷开关：穿透时界面上点不动，这里留个不用进门就能改的入口。"""
        on = not bool(self.data.settings.get("click_through", True))
        self.data.settings["click_through"] = on
        self.save_data()
        self.apply_click_through()
        try:
            self.toast.show(f"鼠标穿透已{'开启' if on else '关闭'}", subtitle="显示设置",
                            seconds=3)
        except Exception:
            pass
        if self.main_window is not None and self.main_window.winfo_exists():
            try:
                self.main_window.tab_settings.refresh()
            except Exception:
                pass

    # ---------------- 倒计时 ----------------
    def after_countdown_change(self) -> None:
        """倒计时数据变动后的统一刷新点。"""
        self.topbar.refresh_countdown()
        self.sync_desktop_countdown()
        if self.main_window is not None and self.main_window.winfo_exists():
            self.main_window.tab_countdown.refresh()

    def sync_desktop_countdown(self) -> None:
        """按「全局开关 + 是否有桌面倒计时」决定桌面贴纸的去留。"""
        want = bool(self.data.settings.get("show_desktop_countdown", False)) \
            and bool(self.data.desktop_countdowns())
        if want:
            if self.desktop_countdown is None or not self.desktop_countdown.winfo_exists():
                self.desktop_countdown = DesktopCountdown(self)
            self.desktop_countdown.refresh()
        elif self.desktop_countdown is not None:
            try:
                self.desktop_countdown.destroy()
            except Exception:
                pass
            self.desktop_countdown = None

    def toggle_desktop_countdown(self) -> None:
        if not self.data.desktop_countdowns():
            self.data.settings["show_desktop_countdown"] = False
            self.show_about_message(
                "还没有桌面倒计时",
                "请到「设置中心 → 倒计时」里，编辑某个倒计时并把「桌面贴纸」设为「是」。")
            return
        on = bool(self.data.settings.get("show_desktop_countdown", False))
        self.data.settings["show_desktop_countdown"] = not on
        self.save_data()
        self.sync_desktop_countdown()

    def show_sponsor(self):
        from .ui.sponsor import show_sponsor

        return show_sponsor(self._dialog_parent(), self)

    # ---------------- 设置中心 ----------------
    def open_settings(self) -> None:
        if self.main_window is None or not self.main_window.winfo_exists():
            self.main_window = MainWindow(self)
        else:
            self.main_window.deiconify()
            self.main_window.lift()
            self.main_window.focus_force()
        self.main_window.refresh_all()

    def main_window_refresh_week(self) -> None:
        if self.main_window is not None and self.main_window.winfo_exists():
            self.main_window.tab_week.refresh()

    def main_window_refresh_course(self) -> None:
        if self.main_window is not None and self.main_window.winfo_exists():
            self.main_window.tab_course.refresh()

    # ---------------- 数据 ----------------
    def save_data(self) -> None:
        try:
            self.store.data = self.data
            self.store.save()
        except Exception as exc:
            self.show_about_message("保存失败", f"写入配置文件失败：{exc}")

    def import_data(self, path: str) -> None:
        data = self.store.import_from(path)
        self._rebind(data)

    def reset_data(self) -> None:
        data = AppData(default_data())
        self.store.data = data
        self.store.save()
        self._rebind(data)

    def _rebind(self, data: AppData) -> None:
        self.data = data
        self.reminder.data = data
        self.reminder.reset()
        self.topbar.refresh()
        if self.main_window is not None and self.main_window.winfo_exists():
            self.main_window.refresh_all()

    # ---------------- 时钟驱动 ----------------
    def on_tick(self, now: datetime) -> None:
        self.reminder.tick(now)
        self._tick_shutdown(now)

    # ---------------- 定时关机 ----------------
    def _tick_shutdown(self, now: datetime) -> None:
        """每秒问一次「该不该排程」；只有刚排上程时才返回事件。"""
        try:
            event = self.shutdown.tick(now, self.data.settings)
        except Exception:
            return
        if not event:
            return
        secs = int(event["seconds"])
        try:
            # 带动作按钮的气泡会自动关掉鼠标穿透，否则「取消关机」按不到
            self.toast.show(
                f"电脑将在 {secs} 秒后关闭",
                subtitle=f"定时关机 · {event['target']:%H:%M} · 未保存内容会丢失",
                seconds=secs + 5,
                action=self.cancel_shutdown,
                action_label="取消关机",
            )
        except Exception:
            pass
        self._refresh_shutdown_ui()

    def cancel_shutdown(self) -> None:
        """撤销已排程的关机：托盘菜单与气泡按钮共用这一个入口。"""
        had = self.shutdown.armed_at is not None
        self.shutdown.cancel()
        try:
            self.toast.show("已取消本次定时关机" if had else "当前没有待执行的关机排程",
                            subtitle="定时关机", seconds=3)
        except Exception:
            pass
        self._refresh_shutdown_ui()

    def _refresh_shutdown_ui(self) -> None:
        mw = self.main_window
        if mw is None or not mw.winfo_exists():
            return
        try:
            mw.tab_settings._refresh_shutdown_hint()
        except Exception:
            pass

    def _on_remind(self, text: str, slot, phase: str) -> None:
        seconds = int(self.data.settings.get("reminder_seconds", 5))
        subtitle = f"{slot.period.name} · {datetime.now():%H:%M}"
        self.toast.show(text, subtitle=subtitle, seconds=seconds)

    # ---------------- 其它 ----------------
    def _dialog_parent(self):
        """优先挂在可见的设置中心上；否则返回根窗口（对话框内部会自行判断可见性）。"""
        mw = self.main_window
        if mw is not None and mw.winfo_exists() and mw.winfo_viewable():
            return mw
        return self.root

    def show_about(self) -> None:
        self.show_about_message(
            f"关于 {config.APP_TITLE}",
            f"{config.APP_TITLE} v{config.APP_VERSION}\n"
            "作者：永恒\n\n"
            "· 桌面顶部常驻半透明玻璃悬浮条，圆角、高度自适应、始终置顶\n"
            "· 24 小时进度条按系统时间实时校准\n"
            "· 每周作息周期 + 特殊作息 + 周课程表\n"
            "· 作息节点非模态提醒，数秒后自动消失\n"
            "· 目标日期倒计时，可显示在悬浮条与桌面贴纸\n"
            "· 定时关机：按「星期 + 时刻」自动关闭电脑，提前 1 分钟提醒并可取消\n"
            "· 单文件绿色版，全程离线，不联网、不上传任何数据\n\n"
            f"数据文件：{config.config_file()}\n\n"
            "提示：关闭设置中心不会退出程序。程序常驻托盘，"
            "需要退出时请在任务栏托盘图标上右键 →「退出程序」。",
        )

    def show_about_message(self, title: str, message: str) -> None:
        from .ui.common import show_info

        show_info(self._dialog_parent(), title, message)

    def quit_app(self) -> None:
        """右键菜单退出：先确认，避免误触。"""
        from .ui.common import ask_yes_no

        if not ask_yes_no(self._dialog_parent(), "退出程序",
                          "退出后顶部悬浮条将不再显示作息与提醒，确定退出？"):
            return
        self.quit_app_now()

    def quit_app_now(self) -> None:
        """不弹确认直接退出（供托盘退出确认后调用）。"""
        self._shutdown()

    def _shutdown(self) -> None:
        # 退出前必须先撤销关机排程：否则「软件关了，电脑照样关」，这是最难解释的坑
        try:
            self.shutdown.cancel()
        except Exception:
            pass
        # 退出路径必须静默保存：save_data 失败会弹提示框，反而卡住退出
        try:
            self.store.data = self.data
            self.store.save()
        except Exception:
            pass
        try:
            self.toast.clear()
        except Exception:
            pass
        try:
            if self.tray is not None:
                self.tray.destroy()       # 必须先移除托盘图标，否则会留下「幽灵图标」
        except Exception:
            pass

        # 兜底：0.8s 后仍在运行则强制结束进程，保证「点了 ✕ 一定关得掉」
        def _force() -> None:
            os._exit(0)

        watchdog = threading.Timer(0.8, _force)
        watchdog.daemon = True
        watchdog.start()

        try:
            self.root.quit()      # 先让 mainloop 返回，停掉 after 任务链
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
