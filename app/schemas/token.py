# app/schemas/token.py
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field("bearer", description="令牌类型，默认 bearer")
    # 可选：过期秒数（如果将来需要在登录接口返回）
    expires_in: Optional[int] = Field(None, description="有效期（秒），可选")
