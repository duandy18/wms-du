# app/api/__init__.py
"""
API package bootstrap.

- 这里不做任何重导出（尤其不再引用已删除的 `app.api.endpoints`）
- 聚合逻辑由 `app/api/router.py` 管理
"""

__all__ = []
