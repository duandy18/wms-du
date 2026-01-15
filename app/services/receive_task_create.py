# app/services/receive_task_create.py
from __future__ import annotations

"""
兼容门面（do-not-delete）：

真实实现已拆分到以下模块：
- app/services/receive_task_create/from_po_full.py
- app/services/receive_task_create/from_po_selected.py
- app/services/receive_task_create/from_order_return.py

保留此文件的唯一目的，是避免全仓库历史 import 路径失效：
    from app.services.receive_task_create import create_for_po

这是一个**刻意的 re-export facade**，不是普通业务模块。
"""

# NOTE:
# This file is an intentional compatibility re-export facade.
# Imports below are intentionally placed after the module docstring.
# Ruff E402 (module level import not at top of file) is suppressed on purpose.
from app.services.receive_task_create.from_po_full import (  # noqa: F401,E402
    create_for_po,
)
from app.services.receive_task_create.from_po_selected import (  # noqa: F401,E402
    create_for_po_selected,
)
from app.services.receive_task_create.from_order_return import (  # noqa: F401,E402
    create_for_order,
)

__all__ = [
    "create_for_po",
    "create_for_po_selected",
    "create_for_order",
]
