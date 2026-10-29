"""系统托盘图标：纯 ctypes 调 Shell_NotifyIcon，零第三方依赖。

设计要点（踩过的坑都在这里）：

1. **窗口过程里绝对不碰 Tcl/Tk。**
   早期的实现是在 WNDPROC 里直接 `TrackPopupMenu`，回来后再 `root.after()`
   派发回调。这条路会让 Tk 在「正在派发 Windows 消息」的中间态被重新进入
   Tcl —— 表现是打包后点菜单项必崩：进程以 0xC0000409（__fastfail /
   /GS 栈保护失败，WER 里叫 BEX）直接消失，且没有任何 Python 栈。
   现在的做法：WNDPROC 只往队列里塞一个事件就返回，菜单与回调都交给
   Tk 的 after 轮询在主循环里执行。

2. **菜单要 DestroyMenu。** 每次右键都 CreatePopupMenu，不销毁就是句柄泄漏。

3. **菜单回调必须先取出来再排队。** TrackPopupMenu 返回后 `_callbacks`
   会被清空，延迟到执行时按索引取就取不到（表现为「点了没反应」）。
"""
from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from typing import Callable

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_APP = 0x8000
WM_TRAYICON = WM_APP + 21
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_NULL = 0x0000
WM_CLOSE = 0x0010

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04
MF_STRING, MF_SEPARATOR = 0x0000, 0x0800
TPM_RETURNCMD, TPM_RIGHTBUTTON, TPM_NONOTIFY = 0x0100, 0x0002, 0x0080
IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE = 0x0010, 0x0040
IDI_APPLICATION = 32512
HWND_MESSAGE = -3

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", GUID)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.CreatePopupMenu.argtypes = []
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]


class TrayIcon:
    """托盘图标 + 原生右键菜单。

    items: [("菜单文字", callback) | None(分隔线), ...]；callback 在 Tk 主线程执行。
    """

    #: Tk 侧的轮询间隔（毫秒）。右键到菜单出现最多晚这么久，肉眼无感。
    POLL_MS = 40

    def __init__(self, root: tk.Tk, tooltip: str, icon: Path | None,
                 items: list[tuple[str, Callable[[], None]] | None]):
        self.root = root
        self.tooltip = tooltip[:127]
        self._items = items
        self._icon_path = str(icon) if icon else ""
        self._hwnd: int = 0
        self._hicon: int = 0
        self._added = False
        self._class_name = f"ClassBellTray_{id(self)}"
        self._wndproc_ref = WNDPROC(self._wndproc)
        self._pending: list[str] = []      # WndProc 只写这里，Tk 侧消费
        self._poll_job = None
        self._alive = False
        self._busy = False                 # 菜单显示中，避免重入
        # 左键单击直接打开设置中心（菜单第一项即「打开设置中心」）
        self._open_cb: Callable[[], None] | None = None
        for item in items:
            if item is not None:
                self._open_cb = item[1]
                break

    # ---------------- 窗口过程（只记录，不执行） ----------------
    def _wndproc(self, hwnd, msg, wparam, lparam) -> int:
        try:
            if msg == WM_TRAYICON:
                event = lparam & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._pending.append("open")
                    return 0
                if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._pending.append("menu")
                    return 0
            elif msg == WM_CLOSE:
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---------------- Tk 侧轮询 ----------------
    def _schedule(self) -> None:
        if not self._alive:
            return
        try:
            self._poll_job = self.root.after(self.POLL_MS, self.poll)
        except Exception:
            self._poll_job = None

    def poll(self) -> None:
        """由 Tk 主循环调用：把 WndProc 记下的事件真正执行掉。"""
        self._poll_job = None
        if not self._alive:
            return
        try:
            while self._pending and not self._busy:
                action = self._pending.pop(0)
                self._busy = True
                try:
                    if action == "menu":
                        self._show_menu()
                    else:
                        self._run(self._open_cb)
                finally:
                    self._busy = False
        except Exception:
            # 托盘线程/回调出错不能让主程序陪葬
            try:
                logging.exception("托盘事件处理失败")
            except Exception:
                pass
        self._schedule()

    # ---------------- 菜单 ----------------
    def _build_menu(self) -> tuple[int, list[Callable[[], None]]]:
        menu = user32.CreatePopupMenu()
        callbacks: list[Callable[[], None]] = []
        for item in self._items:
            if item is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                continue
            text, callback = item
            callbacks.append(callback)
            user32.AppendMenuW(menu, MF_STRING, len(callbacks), text)
        return menu, callbacks

    def _show_menu(self) -> None:
        menu, callbacks = self._build_menu()
        if not menu:
            return
        try:
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            # 先置前台，否则点菜单外部时菜单不会消失
            user32.SetForegroundWindow(self._hwnd)
            cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                                        pt.x, pt.y, 0, self._hwnd, None)
            user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
            if cmd and 0 < cmd <= len(callbacks):
                callback = callbacks[cmd - 1]      # 先取出来再执行
                if callable(callback):
                    self._run(callback)
        finally:
            user32.DestroyMenu(menu)              # 不销毁会泄漏 HMENU

    def _run(self, callback) -> None:  # noqa: ANN001
        """在 Tk 主线程里执行动作，异常走 Tk 的报错通道（写入 error.log）。"""
        if not callable(callback):
            return
        try:
            callback()
        except Exception:
            try:
                self.root.report_callback_exception(*sys.exc_info())
            except Exception:
                try:
                    logging.exception("托盘回调异常")
                except Exception:
                    pass

    # ---------------- 生命周期 ----------------
    def _load_icon(self) -> int:
        if self._icon_path and Path(self._icon_path).exists():
            handle = user32.LoadImageW(None, self._icon_path, IMAGE_ICON, 0, 0,
                                       LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if handle:
                return handle
        return user32.LoadIconW(None, ctypes.c_wchar_p(IDI_APPLICATION))

    def show(self) -> bool:
        if self._added:
            return True
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = 0
        wc.hCursor = 0
        wc.hbrBackground = 0
        wc.lpszMenuName = None
        wc.lpszClassName = self._class_name
        if not user32.RegisterClassW(ctypes.byref(wc)):
            # 已注册过（重复创建）不算失败
            if ctypes.get_last_error() not in (0, 1410):
                return False
        self._hwnd = user32.CreateWindowExW(0, self._class_name, "ClassBellTray", 0,
                                            0, 0, 0, 0, HWND_MESSAGE, 0, hinst, None)
        if not self._hwnd:
            return False

        self._hicon = self._load_icon()
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            return False
        self._added = True
        self._alive = True
        self._schedule()
        return True

    def set_tooltip(self, text: str) -> None:
        self.tooltip = text[:127]
        if not self._added:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_TIP
        nid.szTip = self.tooltip
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def destroy(self) -> None:
        self._alive = False
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None
        if self._added:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self._added = False
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = 0
        try:
            user32.UnregisterClassW(self._class_name, kernel32.GetModuleHandleW(None))
        except Exception:
            pass
