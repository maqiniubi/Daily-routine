"""退出链路测试：退出只能走托盘右键菜单；确认框不能被悬浮条挡住。

两个用例各起一个子进程（退出会终止 mainloop，不能在本进程里测）：
  1. items  —— 断言托盘菜单里有且只有一条「退出程序」，悬浮条上没有退出入口；
  2. x      —— 走退出路径，要求进程自行退出且退出码为 0；
  3. dialog —— 走托盘退出的确认框，要求对话框顶边落在悬浮条下方。
"""
from __future__ import annotations

import ast
import subprocess
import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 测试进程一律用临时数据目录：绝不能读写用户真实的 %APPDATA%\ClassBell
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="classbell_test_")

CHILD = ROOT / "tests" / "_quit_child.py"
FAILED: list[str] = []


def check(cond: bool, label: str) -> None:
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        FAILED.append(label)


def run_child(mode: str, timeout: int = 25) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(CHILD), mode], capture_output=True,
                          text=True, timeout=timeout, encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def case_tray_items() -> None:
    code, out = run_child("items")
    check(code == 0, f"菜单用例正常结束，退出码 {code}")
    labels: list[str] = []
    for line in out.splitlines():
        if line.startswith("TRAY "):
            labels = ast.literal_eval(line[len("TRAY "):].strip())
    check(bool(labels), f"托盘菜单已构建 = {labels}")
    quits = [x for x in labels if "退出" in x]
    check(len(quits) == 1, f"托盘里只有一条退出项 = {quits}")
    check(quits and "唯一" in quits[0], "退出项标注为唯一关闭途径")
    check(not any("退出" in x for x in labels if "赞赏" in x), "赞赏项不夹带退出")


def case_click_x() -> None:
    code, out = run_child("x")
    check(code == 0, f"点击退出后进程退出，退出码 {code}")
    check("EXITED cleanly" in out, "mainloop 正常返回（未走强制兜底）")
    check("ACTION quit_app_now" in out, "退出路径生效")


def case_dialog() -> None:
    code, out = run_child("dialog")
    check(code == 0, f"确认框用例正常结束，退出码 {code}")
    bar = None
    rects: list[tuple[int, int, int, int]] = []
    for line in out.splitlines():
        if line.startswith("BAR "):
            bar = int(line.split()[1])
        elif line.startswith("DIALOG "):
            rects = ast.literal_eval(line[len("DIALOG "):].strip())
    check(bar is not None, f"取到悬浮条高度 = {bar}")
    check(bool(rects), f"确认框已创建 = {rects}")
    if rects and bar:
        top = rects[0][1]
        check(top >= bar - 2, f"确认框顶边 {top} 未被悬浮条（高 {bar}）遮挡")


def main() -> int:
    print("== 托盘菜单 ==")
    case_tray_items()
    print("== 退出执行 ==")
    case_click_x()
    print("== 退出确认框 ==")
    case_dialog()
    print("FAILED:", FAILED if FAILED else "none")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
