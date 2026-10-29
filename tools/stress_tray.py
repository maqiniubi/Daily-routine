"""托盘菜单压力测试：连续多轮「打开菜单 → 选一项」，记录第几轮死、退出码。

用法：python tools/stress_tray.py <exe路径> [轮数]
"""
from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "dist" / "ClassBell.exe")
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
IMG = Path(EXE).name

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowExW.restype = wintypes.HWND
user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.mouse_event.argtypes = [wintypes.DWORD, wintypes.LONG, wintypes.LONG, wintypes.DWORD, ctypes.c_void_p]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]


def pids() -> list[int]:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {IMG}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, encoding="mbcs", errors="replace").stdout
    r = []
    for line in out.splitlines():
        p = [x.strip('"') for x in line.split('","')]
        if len(p) >= 2 and p[1].isdigit():
            r.append(int(p[1]))
    return r


def find_tray() -> int:
    prev = 0
    while True:
        h = user32.FindWindowExW(wintypes.HWND(-3), prev, None, None)
        if not h:
            return 0
        b = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(h, b, 128)
        if b.value.startswith("ClassBellTray_"):
            return h
        prev = h


def find_menu() -> tuple[int, wintypes.RECT]:
    found: list[int] = []
    CB = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _l):  # noqa: ANN001
        b = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, b, 64)
        if b.value == "#32768" and user32.IsWindowVisible(h):
            found.append(h)
        return True

    user32.EnumWindows(CB(cb), 0)
    r = wintypes.RECT()
    if found:
        user32.GetWindowRect(found[-1], ctypes.byref(r))
        return found[-1], r
    return 0, r


def main() -> int:
    subprocess.run(["taskkill", "/IM", IMG, "/F"], capture_output=True)
    time.sleep(1)
    profile = Path(tempfile.mkdtemp(prefix="cb_stress_"))
    src = Path(os.environ["APPDATA"]) / "ClassBell" / "config.json"
    (profile / "ClassBell").mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy(src, profile / "ClassBell" / "config.json")
        print(f"[cfg] 真实配置 {src}")
    env = dict(os.environ)
    env["APPDATA"] = str(profile)
    p = subprocess.Popen([EXE], env=env)
    print(f"[start] pid={p.pid}", flush=True)
    time.sleep(7)

    tray = find_tray()
    print(f"[tray] {tray}", flush=True)
    if not tray:
        print("!! 未找到托盘窗口")
        return 2

    cx, cy = 700, 420
    for i in range(1, ROUNDS + 1):
        item = (i - 1) % 5 + 1
        user32.SetCursorPos(cx, cy)
        time.sleep(0.35)
        user32.PostMessageW(tray, 0x8000 + 21, 0, 0x0205)
        time.sleep(1.0)
        mh, mr = find_menu()
        if not mh:
            print(f"[{i}] 菜单没出现", flush=True)
        else:
            if (mr.left, mr.top) != (cx, cy):
                print(f"[{i}] 注意 菜单位置={mr.left},{mr.top} 与光标不一致", flush=True)
            row = max(18, (mr.bottom - mr.top) // 7)
            tx, ty = mr.left + 40, mr.top + 6 + (item - 1) * row + row // 2
            user32.SetCursorPos(tx, ty)
            time.sleep(0.3)
            user32.mouse_event(0x0002, 0, 0, 0, None)
            time.sleep(0.07)
            user32.mouse_event(0x0004, 0, 0, 0, None)
        time.sleep(1.4)
        a = pids()
        print(f"[{i}] item={item} pids={a} rc={p.poll()}", flush=True)
        if not a:
            print(f"!! 第 {i} 轮崩溃 rc={p.poll()} (0x{(p.poll() or 0) & 0xFFFFFFFF:08X})", flush=True)
            tl = profile / "ClassBell" / "trace.log"
            if tl.exists():
                print("=== trace ===", flush=True)
                print(tl.read_text(encoding="utf-8", errors="replace"), flush=True)
            return 1
    subprocess.run(["taskkill", "/IM", IMG, "/F"], capture_output=True)
    print("[ok] 全部存活")
    return 0


if __name__ == "__main__":
    sys.exit(main())
