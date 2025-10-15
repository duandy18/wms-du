# app/api/endpoints/inbound.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.inbound_service import InboundService
from app.services.putaway_service import PutawayService
from app.schemas.inbound import ReceiveIn, ReceiveOut, PutawayIn  # 你的模型里 PutawayIn 无 item_id

# 依据项目已有依赖获取 AsyncSession
try:
    from app.db.session import get_session  # 常见依赖函数
except Exception:  # 兼容不同项目结构
    async def get_session() -> AsyncSession:  # type: ignore
        raise RuntimeError("get_session dependency not found")

router = APIRouter(prefix="/inbound", tags=["inbound"])


@router.post("/receive", response_model=ReceiveOut)
async def inbound_receive(
    payload: ReceiveIn, session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    入库到 STAGE（复用 InboundService 逻辑）：
    - 自动建 SKU / STAGE
    - UPSERT stocks
    - 写 INBOUND 台账（幂等）
    """
    svc = InboundService()
    data = await svc.receive(
        session=session,
        sku=payload.sku,
        qty=payload.qty,
        ref=payload.ref,
        ref_line=payload.ref_line,
        batch_code=getattr(payload, "batch_code", None),
        production_date=getattr(payload, "production_date", None),
        expiry_date=getattr(payload, "expiry_date", None),
        occurred_at=getattr(payload, "occurred_at", None),
    )
    await session.commit()
    # ReceiveOut 期望包含 item_id / accepted_qty（以及我们后来补的 idempotent 也可被忽略）
    return {"item_id": data["item_id"], "accepted_qty": data["accepted_qty"]}


@router.post("/putaway")
async def inbound_putaway(
    payload: PutawayIn, session: AsyncSession = Depends(get_session)
) -> Dict[str, Any]:
    """
    由入库暂存位搬运到目标库位：
    - 用 payload.sku 解析/创建 item_id（而不是读取不存在的 payload.item_id）
    - 右腿 +1（在 PutawayService 内处理）
    - 成功后返回状态与搬运量
    """
    # 1) 解析/创建 item_id（兼容测试：若先调用了 /inbound/receive 则已存在）
    item_id = await _ensure_item(session, payload.sku)

    # 2) 解析 STAGE 库位（与服务侧策略一致：ILIKE 'STAGE%' → 最小 id → 创建 0）
    stage_id = await _resolve_stage_location(session, preferred_id=0)

    # 3) 搬运（用右腿 +1 的幂等规则；ref_line 可能是 str，需要稳定整数）
    res = await PutawayService.putaway(
        session=session,
        item_id=item_id,
        from_location_id=stage_id,
        to_location_id=payload.to_location_id,
        qty=payload.qty,
        ref=payload.ref,
        ref_line=_to_ref_line_int(payload.ref_line),
    )
    await session.commit()
    return {"status": res.get("status", "ok"), "moved": res.get("moved", payload.qty)}


# ---------------- helpers (与 InboundService 中逻辑保持一致) ----------------

async def _ensure_item(session: AsyncSession, sku: str) -> int:
    row = await session.execute(text("SELECT id FROM items WHERE sku = :sku LIMIT 1"), {"sku": sku})
    got = row.first()
    if got:
        return int(got[0])
    ins = await session.execute(
        text("INSERT INTO items (sku, name) VALUES (:sku, :name) RETURNING id"),
        {"sku": sku, "name": sku},
    )
    return int(ins.scalar())


async def _resolve_stage_location(session: AsyncSession, *, preferred_id: int) -> int:
    # 1) 名称 ILIKE 'STAGE%'
    row = await session.execute(
        text("SELECT id FROM locations WHERE name ILIKE 'STAGE%' ORDER BY id ASC LIMIT 1")
    )
    got = row.first()
    if got:
        return int(got[0])

    # 2) 任意现有库位（最小 id）
    row = await session.execute(text("SELECT id FROM locations ORDER BY id ASC LIMIT 1"))
    got = row.first()
    if got:
        return int(got[0])

    # 3) 创建 preferred_id
    await session.execute(
        text(
            """
            INSERT INTO locations (id, name, warehouse_id)
            VALUES (:i, 'STAGE', 1)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"i": preferred_id},
    )
    return int(preferred_id)


def _to_ref_line_int(ref_line: Any) -> int:
    """把任意类型 ref_line 映射为稳定正整数（int 直返，其他用 CRC32）。"""
    if isinstance(ref_line, int):
        return ref_line
    import zlib

    s = str(ref_line)
    return int(zlib.crc32(s.encode("utf-8")) & 0x7FFFFFFF)
