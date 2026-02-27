# app/api/batch_code_contract.py
from __future__ import annotations

from typing import Dict, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# 非批次商品禁止的历史假码（严格 422）
_FORBIDDEN_FAKE_CODES: Set[str] = {"NOEXP", "NEAR", "FAR", "IDEM"}
# 全局禁止的 “None” 字符串（大小写不敏感）；DB 也有 ck 护栏，但这里要 422 更早拦截
_FORBIDDEN_NONE_TOKEN = "none"


def http_422(detail: str) -> HTTPException:
    # ✅ pytest warning fix: HTTP_422_UNPROCESSABLE_ENTITY deprecated in recent FastAPI/Starlette
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def normalize_optional_batch_code(raw: Optional[str]) -> Optional[str]:
    """
    仅做“查询/内部兼容”级别的归一（不等价于“写入合同容错”）：
      - None -> None
      - "" / "   " -> None
      - "None"（任意大小写）-> None
      - 其它：strip 后返回
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if s.lower() == _FORBIDDEN_NONE_TOKEN:
        return None
    return s


def validate_batch_code_contract(*, requires_batch: bool, batch_code: Optional[str]) -> Optional[str]:
    """
    Phase M：批次合同收紧（422 拦假码），策略真相源来自 items.expiry_policy：

    - requires_batch=True（expiry_policy=REQUIRED）：
        batch_code 必填且非空（strip 后长度>0），禁止 'none'（大小写不敏感）

    - requires_batch=False（expiry_policy=NONE）：
        batch_code 必须为 null（缺省也等价于 null）；
        只要你传了任何值就 422（包括空串/空格/'None'/假码/任意非空字符串）
    """
    if requires_batch:
        s = normalize_optional_batch_code(batch_code)
        if s is None:
            raise http_422("batch_code is required for expiry-policy REQUIRED items.")
        if s.lower() == _FORBIDDEN_NONE_TOKEN:
            raise http_422("batch_code must not be 'none' (case-insensitive).")
        return s

    # 非批次：必须为 null。这里不做“帮你归一”，只要你传了值就 422。
    if batch_code is None:
        return None

    raw = batch_code.strip()
    if raw == "":
        raise http_422(
            "batch_code must be null for expiry-policy NONE items. Do not send empty string."
        )

    up = raw.upper()
    if up in _FORBIDDEN_FAKE_CODES or raw.lower() == _FORBIDDEN_NONE_TOKEN:
        raise http_422(
            "batch_code must be null for expiry-policy NONE items; fake codes are forbidden "
            "(NOEXP/NEAR/FAR/IDEM/None)."
        )

    raise http_422(
        "batch_code must be null for expiry-policy NONE items. Do not send batch_code."
    )


def _requires_batch_from_expiry_policy(expiry_policy: Optional[str]) -> bool:
    # DB enum: 'NONE' | 'REQUIRED'
    return str(expiry_policy or "").upper() == "REQUIRED"


async def fetch_item_expiry_policy_map(session: AsyncSession, item_ids: Set[int]) -> Dict[int, str]:
    """
    真相源：items.expiry_policy（Phase M Rule 层）
    返回：{item_id: 'NONE' | 'REQUIRED'}
    """
    if not item_ids:
        return {}

    rows = await session.execute(
        text("select id, expiry_policy from items where id = any(:ids)"),
        {"ids": list(item_ids)},
    )

    m: Dict[int, str] = {}
    for item_id, expiry_policy in rows.fetchall():
        # expiry_policy 是 enum，psycopg 返回可能是 str / Enum-like；统一转 str
        m[int(item_id)] = str(expiry_policy)
    return m


async def fetch_item_by_sku(session: AsyncSession, sku: str) -> Optional[Tuple[int, bool]]:
    """
    返回 (item_id, requires_batch)
    requires_batch 由 expiry_policy 投影得出。
    """
    s = (sku or "").strip()
    if not s:
        return None

    row = await session.execute(
        text("select id, expiry_policy from items where sku = :sku limit 1"),
        {"sku": s},
    )
    r = row.first()
    if not r:
        return None
    item_id, expiry_policy = r[0], r[1]
    return int(item_id), _requires_batch_from_expiry_policy(str(expiry_policy))
