"""打包产物冒烟测试：启动 dist/ClassBell.exe，检查悬浮条 / 托盘 / 倒计时是否就绪。

不点任何界面，只做进程级观测；用完 taskkill 关闭（程序本身没有别的关闭入口）。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "ClassBell.exe"
SHOTS = ROOT / "shots"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        FAILED.append(label)


def windows_of(pid: int) -> list[tuple[int, str, str, tuple]]:
    found: list[tuple[int, str, str, tuple]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if proc.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        found.append((int(hwnd), buf.value, cls.value, (r.left, r.top, r.right, r.bottom)))
        return True

    user32.EnumWindows(cb, 0)
    return found


def grab(name: str, box: tuple[int, int, int, int]) -> None:
    from PIL import ImageGrab

    SHOTS.mkdir(exist_ok=True)
    ImageGrab.grab(bbox=box).save(str(SHOTS / f"{name}.png"))
    print("  shot:", name, box)


def pids_of(name: str) -> list[int]:
    """onefile 模式下 bootloader 会再起一个子进程，窗口属于子进程。"""
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True, encoding="mbcs", errors="replace").stdout
    pids: list[int] = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def main() -> int:
    if not EXE.exists():
        print("!! 找不到", EXE)
        return 2

    profile = Path(tempfile.mkdtemp(prefix="cb_exe_"))
    env = dict(os.environ)
    env["APPDATA"] = str(profile)
    print("profile:", profile)

    proc = subprocess.Popen([str(EXE)], env=env)
    print("pid:", proc.pid)
    try:
        time.sleep(7)
        check(proc.poll() is None, "进程仍在运行（没有闪退）")

        pids = pids_of(EXE.name)
        print("pids:", pids)
        wins: list[tuple[int, str, str, tuple]] = []
        for pid in pids:
            wins.extend(windows_of(pid))
        print("windows:", wins)
        tops = [w for w in wins if w[3][1] <= 40 and (w[3][2] - w[3][0]) > 600]
        check(bool(tops), "顶部悬浮条已显示")
        if tops:
            w = tops[0]
            sw = user32.GetSystemMetrics(0)
            width = w[3][2] - w[3][0]
            # 玻璃条左右各留一小段边距让壁纸透出来，所以不再严格等于屏宽
            check(width >= sw * 0.96,
                  f"悬浮条接近满宽 {width} / 屏宽 {sw}（两侧留玻璃边距）")
            grab("exe_topbar", (0, 0, sw, w[3][3] + 2))

        icon_file = profile / "ClassBell" / "config.json"
        check(icon_file.exists(), "首次启动写入了配置文件")
        if icon_file.exists():
            import json

            data = json.loads(icon_file.read_text(encoding="utf-8"))
            check(bool(data.get("countdowns")), "默认带一个示例倒计时")
            check("assets" not in str(icon_file), "数据写在用户目录而非 exe 目录")
    finally:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/F"], capture_output=True)
        time.sleep(0.6)

    print("FAILED:", FAILED if FAILED else "none")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
