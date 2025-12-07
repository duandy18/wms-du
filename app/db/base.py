# app/db/base.py
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Iterable, Iterator, List, Set

from sqlalchemy.orm import DeclarativeBase, configure_mappers

log = logging.getLogger("wmsdu.models")


class Base(DeclarativeBase):
    """全局唯一 ORM Base"""

    pass


_INITIALIZED: bool = False  # 防重复初始化


def _iter_model_modules_recursive(pkg_name: str = "app.models") -> Iterator[str]:
    """递归发现 app.models.* 下的所有模块（排除以下划线开头的内部模块）"""
    try:
        pkg = importlib.import_module(pkg_name)
    except ModuleNotFoundError:
        return iter([])

    paths = list(getattr(pkg, "__path__", []))
    if not paths:
        return iter([])

    for _, name, _ in pkgutil.walk_packages(paths, prefix=pkg_name + "."):
        short = name.rsplit(".", 1)[-1]
        if short.startswith("_"):
            continue
        yield name


def _safe_import(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ModuleNotFoundError:
        log.debug("model module not found (skip): %s", mod)
        return False
    except Exception as e:
        log.warning("model import failed: %s (%s)", mod, e)
        return False


def init_models(
    *,
    extra_modules: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
    force: bool = False,
) -> None:
    """
    集中导入模型 + 固化关系映射：
      1) 先显式导入关键模型（保证字符串关系目标类已注册）
      2) 再递归导入 app.models.* 补齐遗漏
      3) 最后统一 configure_mappers()
    """
    global _INITIALIZED
    if _INITIALIZED and not force:
        log.debug("init_models() called again; already initialized, skipping.")
        return

    ex: Set[str] = set(exclude or [])
    loaded: List[str] = []

    explicit_chain = [
        "app.models.item",
        "app.models.batch",
        "app.models.stock",
        "app.models.stock_ledger",
        "app.models.order",
        "app.models.order_item",
        "app.models.order_address",
        "app.models.order_logistics",
        "app.models.store",
        "app.models.warehouse",
        "app.models.platform_shops",
    ]
    for mod in [m for m in explicit_chain if m and m not in ex]:
        if _safe_import(mod):
            loaded.append(mod)

    for mod in _iter_model_modules_recursive("app.models"):
        if mod in ex or mod in loaded:
            continue
        if _safe_import(mod):
            loaded.append(mod)

    if extra_modules:
        for mod in extra_modules:
            if mod in ex or mod in loaded:
                continue
            if _safe_import(mod):
                loaded.append(mod)

    configure_mappers()
    _INITIALIZED = True
    log.info("ORM models initialized & mappers configured (loaded %d modules)", len(loaded))
