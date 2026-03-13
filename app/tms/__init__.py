# app/tms/__init__.py
"""
TMS phase-1 module shell.

本包当前只承载第一阶段模块边界冻结相关能力：
- 领域边界
- 子域所有权
- 对象所有权
- 当前文件归属冻结

后续 Task 2 起，再逐步承接 Shipment / Ledger / Quote 的应用服务收口。
"""

from .phase1_boundary import (
    DomainOwner,
    FileOwnershipRule,
    FrozenOwnership,
    TmsSubdomain,
    find_file_ownership,
    get_frozen_ownership,
)

__all__ = [
    "DomainOwner",
    "FileOwnershipRule",
    "FrozenOwnership",
    "TmsSubdomain",
    "find_file_ownership",
    "get_frozen_ownership",
]
