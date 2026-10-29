"""全局配置：应用信息与数据目录定位。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "ClassBell"
APP_TITLE = "班级作息助手"
APP_VERSION = "1.6.1"
MUTEX_NAME = "Local\\ClassBell_SingleInstance_Mutex"


def exe_dir() -> Path:
    """程序所在目录（打包后为 exe 目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """数据目录：便携模式下用 exe 同级的 data/，否则用 %APPDATA%\\ClassBell。"""
    base = exe_dir()
    if (base / "portable.txt").exists():
        d = base / "data"
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("1", encoding="utf-8")
            probe.unlink()
            return d
        except Exception:
            pass

    root = Path(os.environ.get("APPDATA") or Path.home())
    d = root / APP_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        d = Path(os.environ.get("TEMP", str(Path.home()))) / APP_NAME
        d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return data_dir() / "config.json"


def resource_path(*parts: str) -> Path:
    """打包后资源位于 sys._MEIPASS，源码运行时位于项目根目录。"""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)
