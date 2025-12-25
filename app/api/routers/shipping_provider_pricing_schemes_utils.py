# app/api/routers/shipping_provider_pricing_schemes_utils.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.user_service import AuthorizationError, UserService


# -----------------------
# Permission
# -----------------------
def check_perm(db: Session, user, perm: str) -> None:
    svc = UserService(db)
    try:
        svc.check_permission(user, [perm])
    except AuthorizationError:
        raise HTTPException(status_code=403, detail="Not authorized")


# -----------------------
# Validators / Normalizers
# -----------------------
_ALLOWED_MEMBER_LEVELS = {"province", "city", "district", "text"}


def norm_level(v: str) -> str:
    lvl = (v or "").strip().lower()
    if lvl not in _ALLOWED_MEMBER_LEVELS:
        raise HTTPException(
            status_code=422, detail="level must be one of: province/city/district/text"
        )
    return lvl


def norm_nonempty(v: Optional[str], field: str) -> str:
    t = (v or "").strip()
    if not t:
        raise HTTPException(status_code=422, detail=f"{field} is required")
    return t


def validate_effective_window(
    effective_from: Optional[datetime], effective_to: Optional[datetime]
) -> None:
    if effective_from is not None and effective_to is not None:
        if effective_to < effective_from:
            raise HTTPException(status_code=422, detail="effective_to must be >= effective_from")


def clean_list_str(values: Optional[List[str]]) -> List[str]:
    """
    - strip
    - drop empty
    - keep stable order + de-dup
    """
    out: List[str] = []
    seen = set()
    for x in values or []:
        t = (x or "").strip()
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


# -----------------------
# Phase 4.3: segments_json validator (hard alignment)
# -----------------------
def _parse_decimal_str(s: str, field: str, idx: int) -> Decimal:
    t = (s or "").strip()
    if not t:
        raise HTTPException(status_code=422, detail=f"segments_json[{idx}].{field} is required")
    try:
        d = Decimal(t)
    except (InvalidOperation, ValueError):
        raise HTTPException(
            status_code=422, detail=f"segments_json[{idx}].{field} must be a number string"
        )
    return d


def _fmt_decimal(d: Decimal) -> str:
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def normalize_segments_json(raw: object) -> Optional[List[dict]]:
    """
    接受形状：[{min:"0",max:"1"}, ... {min:"2",max:""}]
    强约束（为了“刚性对齐”）：
      - 必须是 list 且非空
      - min 必填、>=0
      - max 可空(=∞)；非空则必须 > min
      - 必须按 min 升序排列（不偷偷排序）
      - 必须连续：next.min == prev.max（prev.max 不能为空）
      - ∞ 段必须是最后一段
      - 第一段 min 必须为 0
    返回：规范化 dict 列表（写入 JSONB）
    """
    if raw is None:
        return None

    if not isinstance(raw, list):
        raise HTTPException(status_code=422, detail="segments_json must be a list")

    if len(raw) == 0:
        raise HTTPException(status_code=422, detail="segments_json must have at least 1 segment")

    norm: List[Tuple[Decimal, Optional[Decimal], dict]] = []

    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail=f"segments_json[{i}] must be an object")

        min_raw = str(item.get("min", "")).strip()
        max_raw = str(item.get("max", "")).strip()

        mn = _parse_decimal_str(min_raw, "min", i)
        if mn < 0:
            raise HTTPException(status_code=422, detail=f"segments_json[{i}].min must be >= 0")

        mx: Optional[Decimal] = None
        if max_raw != "":
            mx = _parse_decimal_str(max_raw, "max", i)
            if mx <= mn:
                raise HTTPException(status_code=422, detail=f"segments_json[{i}].max must be > min")

        norm.append(
            (mn, mx, {"min": _fmt_decimal(mn), "max": "" if mx is None else _fmt_decimal(mx)})
        )

    if norm[0][0] != Decimal("0"):
        raise HTTPException(status_code=422, detail="segments_json[0].min must be 0")

    # 升序检查（不自动排序）
    for i in range(1, len(norm)):
        if norm[i][0] < norm[i - 1][0]:
            raise HTTPException(
                status_code=422, detail="segments_json must be ordered by min ascending"
            )

    # 连续性 + ∞ 段最后
    for i in range(1, len(norm)):
        prev_mn, prev_mx, _ = norm[i - 1]
        cur_mn, cur_mx, _ = norm[i]

        if prev_mx is None:
            raise HTTPException(
                status_code=422, detail="segments_json has INF segment; it must be the last segment"
            )

        if cur_mn != prev_mx:
            raise HTTPException(
                status_code=422,
                detail=f"segments_json must be contiguous: segments_json[{i}].min must equal previous max",
            )

        if cur_mx is not None and cur_mx <= cur_mn:
            raise HTTPException(status_code=422, detail=f"segments_json[{i}].max must be > min")

    return [x[2] for x in norm]
