# Split note:
# 本目录是 inventory_adjustment 模块的物理收口层。
# 当前阶段先以 re-export / 聚合为主，方便按页面查看 contract / model / repo / router / service。
# 后续如确认稳定，再逐步把真实实现迁入本目录。


from importlib import import_module
from types import ModuleType
from typing import Any

_SRC: ModuleType = import_module("app.wms.receiving.repos.inbound_operation_write_repo")
__all__ = list(getattr(_SRC, "__all__", ()))


def __getattr__(name: str) -> Any:
    return getattr(_SRC, name)


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(dir(_SRC)))
