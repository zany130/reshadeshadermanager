"""Global ``config.json`` (defaults + load/save)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, Mapping

from reshade_shader_manager.core.paths import RsmPaths


@dataclass
class AppConfig:
    default_reshade_version: str = "latest"
    default_variant: str = "standard"  # "standard" | "addon"
    create_ini_if_missing: bool = True
    shader_download_enabled: bool = True
    pcgw_cache_ttl_hours: float = 24.0

    def validate(self) -> None:
        if self.default_variant not in ("standard", "addon"):
            raise ValueError(f"invalid default_variant: {self.default_variant!r}")
        if self.pcgw_cache_ttl_hours < 0:
            raise ValueError("pcgw_cache_ttl_hours must be >= 0")

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_mapping(m: Mapping[str, Any]) -> AppConfig:
        allowed = {f.name for f in fields(AppConfig)}
        extra = set(m.keys()) - allowed
        if extra:
            raise ValueError(f"unknown config keys: {sorted(extra)}")
        return AppConfig(
            default_reshade_version=str(m.get("default_reshade_version", AppConfig.default_reshade_version)),
            default_variant=str(m.get("default_variant", AppConfig.default_variant)),
            create_ini_if_missing=bool(m.get("create_ini_if_missing", AppConfig.create_ini_if_missing)),
            shader_download_enabled=bool(m.get("shader_download_enabled", AppConfig.shader_download_enabled)),
            pcgw_cache_ttl_hours=float(m.get("pcgw_cache_ttl_hours", AppConfig.pcgw_cache_ttl_hours)),
        )


def load_config(paths: RsmPaths) -> AppConfig:
    path = paths.config_json()
    if not path.is_file():
        cfg = AppConfig()
        cfg.validate()
        return cfg
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("config.json must be a JSON object")
    cfg = AppConfig.from_mapping(data)
    cfg.validate()
    return cfg


def save_config(paths: RsmPaths, cfg: AppConfig) -> None:
    cfg.validate()
    path = paths.config_json()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cfg.to_json_dict(), f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)
