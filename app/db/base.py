# app/db/base.py
from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import DeclarativeBase, configure_mappers

log = logging.getLogger("wmsdu.models")


class Base(DeclarativeBase):
    """全局唯一 ORM Base（全项目统一 from app.db.base import Base）"""
    pass


def _iter_model_modules() -> list[str]:
    """
    自动发现 app/models 下的所有模块（排除 __init__.py），
    以避免手工维护“白名单”时漏掉新模型。
    """
    pkg_name = "app.models"
    try:
        pkg = importlib.import_module(pkg_name)
    except ModuleNotFoundError:
        return []

    modules: list[str] = []
    # 支持包为命名空间或普通包的两种情况
    paths = list(getattr(pkg, "__path__", []))
    for finder, name, ispkg in pkgutil.iter_modules(paths):
        if name.startswith("_"):
            continue
        full = f"{pkg_name}.{name}"
        modules.append(full)
    return modules


def _eager_import(modules: Iterable[str]) -> None:
    for mod in modules:
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError:
            # 分支差异或未启用子域：跳过即可
            continue
        except Exception as e:
            # 不阻断启动；需要时可提升为 warning
            log.debug("model import failed: %s (%s)", mod, e)


def init_models(extra_modules: Iterable[str] | None = None) -> None:
    """
    集中导入模型 + 触发关系映射校验。
    - 在应用/脚本启动时调用一次（FastAPI：app/main.py；脚本：见下文替换版）
    - 如有特殊模型不在 app.models 包下，可通过 extra_modules 追加
    """
    discovered = _iter_model_modules()
    _eager_import(discovered)

    if extra_modules:
        _eager_import(extra_modules)

    # 关键：强制配置所有 mapper；若 relationship("ClassName") 无法解析会在此抛出
    configure_mappers()
    log.info("ORM models initialized & mappers configured (loaded %d modules)", len(discovered))
