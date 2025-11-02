# app/api/__init__.py
"""
让旧代码可以 `from app.api import api_router`。
"""
from __future__ import annotations

from .endpoints import api_router  # re-export
