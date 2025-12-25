# app/api/routers/user_helpers.py
from __future__ import annotations

import os


def token_expires_in_seconds() -> int:
    """
    给前端/调用方一个清晰的 expires_in（秒）。
    - 优先读环境变量 ACCESS_TOKEN_EXPIRE_MINUTES
    - 若未配置，则默认 60 分钟
    """
    try:
        mins = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    except Exception:
        mins = 60
    if mins <= 0:
        mins = 60
    return mins * 60
