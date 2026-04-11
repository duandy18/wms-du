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

# Phase 5：这些 legacy 模型对应的表在当前 DB/主线迁移中不存在，
# 若被导入会污染 Base.metadata，触发 alembic-check 误报 add_table。
# ✅ 规则：主线 metadata 禁止加载它们（不允许双真相 / 不复活旧表）。
_DEFAULT_EXCLUDE: Set[str] = {
    "app.models.batch",
}

# Phase M-5：表名级别的 legacy 黑名单（防止未来模块改名/移动导致 ex 失效）
# 一旦被导入，必须从 Base.metadata 移除，避免 alembic-check 噪音。
_LEGACY_TABLE_NAMES: Set[str] = {
    "stocks",
    "batches",
    "snapshots",  # 若未来有人误复活 v1 快照表
}


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


def _purge_legacy_tables_from_metadata() -> None:
    """
    防腐层：即便某个 legacy 模型被意外导入（例如改名/移动导致 _DEFAULT_EXCLUDE 失效），
    也要保证 Base.metadata 不包含这些 legacy 表名，以免 alembic-check / autogenerate 误报。
    """
    for tname in list(Base.metadata.tables.keys()):
        if tname in _LEGACY_TABLE_NAMES:
            Base.metadata.remove(Base.metadata.tables[tname])
            log.warning("purged legacy table from Base.metadata: %s", tname)


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

    Phase 5 约束（硬）：
    - 主线 metadata 禁止加载 legacy 的 batch（对应表不存在），避免 alembic-check 误报。
    """
    global _INITIALIZED
    if _INITIALIZED and not force:
        log.debug("init_models() called again; already initialized, skipping.")
        return

    # 合并 exclude：调用方 exclude + 默认排除（Phase 5 legacy）
    ex: Set[str] = set(exclude or [])
    ex |= set(_DEFAULT_EXCLUDE)

    loaded: List[str] = []

    # ✅ 显式加载链：只放“主线真相表”的模型（避免把 legacy 表带进 metadata）
    explicit_chain = [
        "app.pms.suppliers.models.supplier",
        "app.pms.suppliers.models.supplier_contact",
        "app.pms.items.models.item",
        "app.pms.items.models.item_uom",
        "app.pms.items.models.item_barcode",
        "app.wms.stock.models.lot",
        "app.wms.stock.models.stock_lot",
        "app.wms.ledger.models.stock_ledger",
        "app.wms.stock.models.stock_snapshot",
        "app.models.order",
        "app.models.order_item",
        "app.models.order_address",
        "app.models.order_logistics",
        "app.models.order_fulfillment",
        "app.models.store",
        "app.models.warehouse",
        "app.models.platform_shops",
    ]
    for mod in [m for m in explicit_chain if m and m not in ex]:
        if _safe_import(mod):
            loaded.append(mod)

    for pkg_name in ("app.models", "app.pms.items.models", "app.pms.suppliers.models"):
        for mod in _iter_model_modules_recursive(pkg_name):
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

    _purge_legacy_tables_from_metadata()

    configure_mappers()
    _INITIALIZED = True
    log.info("ORM models initialized & mappers configured (loaded %d modules)", len(loaded))
