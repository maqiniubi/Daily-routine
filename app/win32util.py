"""Win32 小工具：置顶守护、DPI、单实例、开机自启。全部基于 ctypes，无第三方依赖。"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

HWND_TOPMOST = wintypes.HWND(-1)
HWND_BOTTOM = wintypes.HWND(1)
GWL_STYLE = -16
WS_CHILD = 0x40000000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020      # 命中测试穿透：鼠标事件落到下面的窗口
WS_EX_LAYERED = 0x00080000          # 分层窗口（alpha / 抠色都需要）
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

# 显式声明原型：64 位下 HWND/HANDLE 若按默认 c_int 返回会被截断
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.SetParent.restype = wintypes.HWND
user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
user32.SetWindowRgn.restype = ctypes.c_int
user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]


def enable_dpi_awareness() -> None:
    """系统级 DPI 感知，避免高分屏下界面模糊。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def hwnd_of(window) -> int:
    """取得 Tk 窗口对应的顶层 HWND。"""
    try:
        window.update_idletasks()
        return int(window.tk.call("wm", "frame", window._w), 16)
    except Exception:
        try:
            hwnd = user32.GetParent(window.winfo_id())
            return hwnd or window.winfo_id()
        except Exception:
            return 0


def make_tool_window(hwnd: int) -> None:
    """标记为工具窗口：不出现在 Alt+Tab / 任务栏。"""
    if not hwnd:
        return
    try:
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        style |= WS_EX_TOOLWINDOW
        user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
    except Exception:
        pass


def is_minimized(hwnd: int) -> bool:
    if not hwnd:
        return False
    try:
        return bool(user32.IsIconic(wintypes.HWND(hwnd)))
    except Exception:
        return False


def restore_no_activate(hwnd: int) -> None:
    """把被最小化的窗口恢复显示但不抢焦点（Win+D 后贴纸靠它自己回来）。"""
    if not hwnd:
        return
    try:
        user32.ShowWindow(wintypes.HWND(hwnd), 4)      # SW_SHOWNOACTIVATE
    except Exception:
        pass


def push_topmost(hwnd: int) -> None:
    """把窗口重新压到 Z 序最顶层，不抢焦点、不改变位置尺寸。"""
    if not hwnd:
        return
    try:
        user32.SetWindowPos(
            wintypes.HWND(hwnd), HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
    except Exception:
        pass


class SingleInstance:
    """命名互斥体，防止重复启动。"""

    def __init__(self, name: str):
        self._handle = None
        self._name = name

    def acquire(self) -> bool:
        try:
            self._handle = kernel32.CreateMutexW(None, False, self._name)
            return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
        except Exception:
            return True

    def release(self) -> None:
        if self._handle:
            try:
                kernel32.CloseHandle(self._handle)
            except Exception:
                pass
            self._handle = None


def set_autostart(enable: bool, exe_path: str | None = None) -> bool:
    """写入 / 删除 HKCU\\...\\Run 启动项，无需管理员权限。"""
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        name = "ClassBell"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                target = exe_path or sys.executable
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, f'"{target}"')
            else:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, "ClassBell")
            return True
    except Exception:
        return False


def set_dark_titlebar(hwnd: int, dark: bool = True) -> None:
    """Win10 1809+ / Win11：把系统标题栏切成深色，贴合黑白主题。"""
    if not hwnd:
        return
    try:
        dwm = ctypes.WinDLL("dwmapi")
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attr, ctypes.byref(value),
                                         ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


def set_round_region(hwnd: int, width: int, height: int, radius: int) -> bool:
    """把窗口裁成圆角矩形（真裁剪，四角完全透明）。

    tkinter 做不到「半透明 + 真圆角」同时成立：`-alpha` 走
    SetLayeredWindowAttributes(LWA_ALPHA)，`-transparentcolor` 走
    LWA_COLORKEY，两者互斥。而 SetWindowRgn 是窗口区域的几何裁剪，
    与 layered 叠加并不冲突，所以圆角用 region、半透明用 alpha。

    注意：设置成功后 region 归系统所有，不能再 DeleteObject。
    """
    if not hwnd or width <= 0 or height <= 0:
        return False
    r = max(0, int(radius))
    try:
        hrgn = gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, r * 2, r * 2)
        if not hrgn:
            return False
        if not user32.SetWindowRgn(wintypes.HWND(hwnd), hrgn, True):
            gdi32.DeleteObject(hrgn)
            return False
        return True
    except Exception:
        return False


def set_window_alpha(window, alpha: float) -> None:
    """整窗不透明度（0.0~1.0）。值越接近 1 越不透明。"""
    try:
        window.attributes("-alpha", max(0.35, min(1.0, float(alpha))))
    except Exception:
        pass


def set_click_through(target, enable: bool) -> bool:
    """鼠标穿透：开启后点击/滚轮直接落到下面的窗口，本窗口收不到任何鼠标消息。

    实现是给窗口加 `WS_EX_TRANSPARENT`——命中测试阶段被跳过，于是
    `WindowFromPoint` 会返回它下面的窗口。再补一个 `WS_EX_LAYERED`：
    分层窗口 + TRANSPARENT 是 Windows 上最经典也最稳的穿透组合
    （悬浮条 / 气泡 / 贴纸本来就已经是 layered，加这个只是幂等）。

    改完 exstyle 必须走一次 `SetWindowPos(SWP_FRAMECHANGED)`，
    否则命中区域要等到下一次移动/缩放才刷新。

    target 可以是 tkinter 窗口，也可以直接是 HWND。
    """
    try:
        hwnd = int(target) if isinstance(target, int) else hwnd_of(target)
    except Exception:
        return False
    if not hwnd:
        return False
    try:
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        if enable:
            new = style | WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            new = style & ~WS_EX_TRANSPARENT
        if new != style:
            user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, new)
        user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
                            | SWP_FRAMECHANGED)
        return True
    except Exception:
        return False


def is_click_through(target) -> bool:
    """读回穿透状态，供测试与自检使用。"""
    try:
        hwnd = int(target) if isinstance(target, int) else hwnd_of(target)
        if not hwnd:
            return False
        style = user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        return bool(style & WS_EX_TRANSPARENT)
    except Exception:
        return False
