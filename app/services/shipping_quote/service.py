# app/services/shipping_quote/service.py
from __future__ import annotations

# 兼容旧 import 路径：外部仍可 from app.services.shipping_quote.service import calc_quote/recommend_quotes

from .calc import calc_quote
from .recommend import recommend_quotes

__all__ = ["calc_quote", "recommend_quotes"]
