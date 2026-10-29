"""JSON 持久化：原子写入 + 备份 + 导入导出。"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from . import config
from .models import AppData


class Store:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.config_file()
        self.data: AppData = AppData()

    # ---------- 读写 ----------
    def load(self) -> AppData:
        raw = None
        if self.path.exists():
            raw = self._read_json(self.path)
        if raw is None:
            bak = self.path.with_suffix(".bak.json")
            if bak.exists():
                raw = self._read_json(bak)
        try:
            self.data = AppData(raw)
        except Exception:
            self.data = AppData()
        try:
            self.data.validate()
        except Exception:
            pass
        return self.data

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.data.to_dict()
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
        if self.path.exists():
            try:
                shutil.copyfile(self.path, self.path.with_suffix(".bak.json"))
            except Exception:
                pass
        tmp.replace(self.path)

    # ---------- 导入导出 ----------
    def export_to(self, target: str) -> None:
        suffix = datetime.now().strftime("%Y%m%d")
        payload = self.data.to_dict()
        if not target.lower().endswith(".json"):
            target = f"{target}.json"
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        _ = suffix

    def import_from(self, source: str) -> AppData:
        raw = self._read_json(Path(source))
        if raw is None:
            raise ValueError("文件无法解析为合法的 JSON")
        if "schedules" not in raw:
            raise ValueError("JSON 中缺少 schedules 字段，不是本软件的作息表文件")
        data = AppData(raw)
        data.validate()
        self.data = data
        self.save()
        return data
