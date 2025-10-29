# app/api/router.py
"""
让旧代码可以 `from app.api.router import api_router`。
本文件仅把 endpoints/__init__.py 暴露出来。
"""
from __future__ import annotations

from app.api.endpoints import api_router  # re-export
