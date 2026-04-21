# Split note:
# return_inbound 模块中的 ReturnTask ORM 不再重复定义。
# 单一 ORM 真相保持在 app.models.return_task。
# 本文件仅做显式 re-export，避免 registry / metadata 双注册。

from __future__ import annotations

from app.models.return_task import ReturnTask, ReturnTaskLine

__all__ = [
    "ReturnTask",
    "ReturnTaskLine",
]
