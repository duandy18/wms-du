# app/services/internal_outbound_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.internal_outbound import InternalOutboundDoc, InternalOutboundLine
from app.services.audit_writer import AuditEventWriter
from app.services.stock_service import StockService

UTC = timezone.utc


class InternalOutboundService:
    """
    内部出库服务（Internal Outbound）：

    目标：让样品 / 内部领用 / 报废等“非订单出库”具备：
      - 单据头（doc_head）
      - 单据行（doc_lines）
      - 状态（DRAFT → CONFIRMED / CANCELED）
      - 台账（stock_ledger）
      - trace_id（TraceStudio 可追踪）
      - 审计事件（audit_events）

    关键设计：
      - 单据头记录领取人（recipient_name），确认前必须填写；
      - 行可以指定 batch_code，不指定时走 FEFO 扣减（与 ship 逻辑一致）；
      - 确认时统一调用 StockService.adjust(delta<0, reason="INTERNAL_OUT")。
    """

    def __init__(self, stock_svc: Optional[StockService] = None) -> None:
        self.stock_svc = stock_svc or StockService()

    # ------------------------------------------------------------------ #
    # 工具：doc_no & trace_id 生成                                       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _gen_doc_no(warehouse_id: int) -> str:
        now = datetime.now(UTC)
        # 简单可读单号：INT-OUT:WH{warehouse_id}:{YYYYMMDDHHMMSS}
        return f"INT-OUT:WH{warehouse_id}:{now.strftime('%Y%m%d%H%M%S')}"

    @staticmethod
    def _gen_trace_id(warehouse_id: int, doc_no: str) -> str:
        # trace_id 单独一套格式，便于 TraceStudio 聚合
        return f"INT-OUT:{warehouse_id}:{doc_no}"

    # ------------------------------------------------------------------ #
    # 创建内部出库单                                                     #
    # ------------------------------------------------------------------ #
    async def create_doc(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        doc_type: str,
        recipient_name: str,
        recipient_type: Optional[str] = None,
        recipient_note: Optional[str] = None,
        note: Optional[str] = None,
        created_by: Optional[int] = None,
        trace_id: Optional[str] = None,
    ) -> InternalOutboundDoc:
        """
        创建一张内部出库单（头）：

        - 必须指定 warehouse_id / doc_type / recipient_name；
        - 初始状态为 DRAFT；
        - 生成 doc_no（(warehouse_id, doc_no) 唯一）；
        - 若未显式传 trace_id，则基于 warehouse_id + doc_no 生成；
        - created_at 必须显式设置，避免触发 NOT NULL 约束。
        """
        if not recipient_name or not recipient_name.strip():
            raise ValueError("内部出库单必须填写领取人姓名（recipient_name）")

        doc_no = self._gen_doc_no(warehouse_id)
        ti = trace_id or self._gen_trace_id(warehouse_id, doc_no)
        now = datetime.now(UTC)

        doc = InternalOutboundDoc(
            warehouse_id=warehouse_id,
            doc_no=doc_no,
            doc_type=doc_type,
            status="DRAFT",
            recipient_name=recipient_name.strip(),
            recipient_type=recipient_type,
            recipient_note=recipient_note,
            note=note,
            created_by=created_by,
            created_at=now,
            trace_id=ti,
        )
        session.add(doc)
        await session.flush()

        # 审计：创建内部出库单
        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="INTERNAL_OUT_CREATED",
            ref=doc_no,
            trace_id=ti,
            meta={
                "doc_id": doc.id,
                "doc_no": doc_no,
                "warehouse_id": warehouse_id,
                "doc_type": doc.doc_type,
                "recipient_name": doc.recipient_name,
            },
            auto_commit=False,
        )

        return await self.get_with_lines(session, doc.id)

    # ------------------------------------------------------------------ #
    # 查询：带行读取单据                                                 #
    # ------------------------------------------------------------------ #
    async def get_with_lines(
        self,
        session: AsyncSession,
        doc_id: int,
        *,
        for_update: bool = False,
    ) -> InternalOutboundDoc:
        stmt = (
            select(InternalOutboundDoc)
            .options(selectinload(InternalOutboundDoc.lines))
            .where(InternalOutboundDoc.id == doc_id)
        )
        if for_update:
            stmt = stmt.with_for_update()

        res = await session.execute(stmt)
        doc = res.scalars().first()
        if doc is None:
            raise ValueError(f"InternalOutboundDoc not found: id={doc_id}")

        if doc.lines:
            doc.lines.sort(key=lambda ln: (ln.line_no, ln.id))
        return doc

    # ------------------------------------------------------------------ #
    # 行操作：新增 / 累加行                                              #
    # ------------------------------------------------------------------ #
    async def upsert_line(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str] = None,
        uom: Optional[str] = None,
        note: Optional[str] = None,
    ) -> InternalOutboundDoc:
        """
        对内部出库单新增或累加一行：

        - 仅允许在 DRAFT 状态下修改；
        - 若同一 doc 下已存在 (item_id, batch_code) 则累加 requested_qty；
        - 否则新建一行，line_no = 当前最大行号 + 1；
        - qty 可为正数（新增）或负数（减少），但最终 requested_qty 不得小于 0。
        """
        if qty == 0:
            return await self.get_with_lines(session, doc_id)

        doc = await self.get_with_lines(session, doc_id, for_update=True)
        if doc.status != "DRAFT":
            raise ValueError(f"内部出库单 {doc.id} 状态为 {doc.status}，不能修改行")

        norm_code = batch_code.strip() if batch_code is not None else None

        target: Optional[InternalOutboundLine] = None
        for ln in doc.lines or []:
            if ln.item_id == item_id and (ln.batch_code or "") == (norm_code or ""):
                target = ln
                break

        if target is None:
            next_line_no = 1
            if doc.lines:
                next_line_no = max(ln.line_no for ln in doc.lines) + 1

            target = InternalOutboundLine(
                doc_id=doc.id,
                line_no=next_line_no,
                item_id=item_id,
                batch_code=norm_code,
                requested_qty=int(qty),
                confirmed_qty=None,
                uom=uom,
                note=note,
            )
            if target.requested_qty < 0:
                raise ValueError(
                    f"内部出库行数量不能为负：item_id={item_id}, batch_code={norm_code}, "
                    f"after={target.requested_qty}"
                )
            session.add(target)
        else:
            target.requested_qty += int(qty)
            if target.requested_qty < 0:
                raise ValueError(
                    f"内部出库行数量不能为负：item_id={item_id}, batch_code={norm_code}, "
                    f"after={target.requested_qty}"
                )

            if norm_code is not None and not target.batch_code:
                target.batch_code = norm_code
            if note is not None:
                target.note = note
            if uom is not None:
                target.uom = uom

        await session.flush()
        return await self.get_with_lines(session, doc.id)

    # ------------------------------------------------------------------ #
    # 工具：按 FEFO 扣减若干数量（内部出库）                             #
    # ------------------------------------------------------------------ #
    async def _fefo_deduct_internal(
        self,
        session: AsyncSession,
        *,
        warehouse_id: int,
        item_id: int,
        total_qty: int,
        ref: str,
        base_ref_line: int,
        trace_id: Optional[str],
    ) -> None:
        """
        按 FEFO 从 stocks 扣减 total_qty：

        - 逻辑与 StockService.ship_commit_direct 中的 FEFO 选择类似；
        - 每次选一行 (batch_code, qty)，调用 StockService.adjust(reason="INTERNAL_OUT")；
        - ref_line 使用 base_ref_line * 100 + idx。
        """
        remain = total_qty
        idx = 0
        now = datetime.now(UTC)

        while remain > 0:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT s.batch_code, s.qty
                          FROM stocks s
                          LEFT JOIN batches b
                            ON b.item_id      = s.item_id
                           AND b.warehouse_id = s.warehouse_id
                           AND b.batch_code   = s.batch_code
                         WHERE s.item_id = :i
                           AND s.warehouse_id = :w
                           AND s.qty > 0
                         ORDER BY b.expiry_date ASC NULLS LAST, s.id ASC
                         LIMIT 1
                        """
                    ),
                    {"i": item_id, "w": int(warehouse_id)},
                )
            ).first()

            if not row:
                raise ValueError(
                    f"内部出库 FEFO 扣减失败：库存不足 item_id={item_id}, remain={remain}"
                )

            batch_code, on_hand = str(row[0]), int(row[1])
            take = min(remain, on_hand)
            idx += 1

            await self.stock_svc.adjust(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                delta=-take,
                reason="INTERNAL_OUT",
                ref=ref,
                ref_line=base_ref_line * 100 + idx,
                occurred_at=now,
                batch_code=batch_code,
                trace_id=trace_id,
            )

            remain -= take

    # ------------------------------------------------------------------ #
    # 确认：正式扣库存 + 写台账 + 审计                                  #
    # ------------------------------------------------------------------ #
    async def confirm(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        user_id: Optional[int] = None,
        occurred_at: Optional[datetime] = None,
    ) -> InternalOutboundDoc:
        """
        确认内部出库单：

        - 仅允许 DRAFT → CONFIRMED；
        - 要求 recipient_name 非空；
        - 遍历行，根据 confirmed_qty 或 requested_qty 作为出库数量：
            * 若指定 batch_code → 直接扣该批次；
            * 若未指定 batch_code → 按 FEFO 扣减；
        - 统一 reason="INTERNAL_OUT"，ref=doc.doc_no；
        - 写 audit_events(INTERNAL_OUT_CONFIRMED)。
        """
        doc = await self.get_with_lines(session, doc_id, for_update=True)

        if doc.status != "DRAFT":
            raise ValueError(f"内部出库单 {doc.id} 状态为 {doc.status}，不能重复确认")

        if not doc.recipient_name or not doc.recipient_name.strip():
            raise ValueError(
                f"内部出库单 {doc.id} 未填写领取人姓名（recipient_name），禁止确认出库"
            )

        if not doc.lines:
            raise ValueError(f"内部出库单 {doc.id} 没有任何行，无法确认出库")

        now = occurred_at or datetime.now(UTC)
        ref = doc.doc_no
        trace_id = doc.trace_id or self._gen_trace_id(doc.warehouse_id, doc.doc_no)

        for line in doc.lines:
            qty = line.confirmed_qty if line.confirmed_qty is not None else line.requested_qty
            qty = int(qty or 0)
            if qty <= 0:
                continue

            if line.batch_code:
                await self.stock_svc.adjust(
                    session=session,
                    item_id=line.item_id,
                    warehouse_id=doc.warehouse_id,
                    delta=-qty,
                    reason="INTERNAL_OUT",
                    ref=ref,
                    ref_line=line.line_no,
                    occurred_at=now,
                    batch_code=str(line.batch_code).strip(),
                    trace_id=trace_id,
                )
            else:
                await self._fefo_deduct_internal(
                    session=session,
                    warehouse_id=doc.warehouse_id,
                    item_id=line.item_id,
                    total_qty=qty,
                    ref=ref,
                    base_ref_line=line.line_no,
                    trace_id=trace_id,
                )

        doc.status = "CONFIRMED"
        doc.confirmed_by = user_id
        doc.confirmed_at = now
        doc.trace_id = trace_id

        await session.flush()

        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="INTERNAL_OUT_CONFIRMED",
            ref=ref,
            trace_id=trace_id,
            meta={
                "doc_id": doc.id,
                "doc_no": doc.doc_no,
                "warehouse_id": doc.warehouse_id,
                "doc_type": doc.doc_type,
                "recipient_name": doc.recipient_name,
                "lines": [
                    {
                        "line_no": ln.line_no,
                        "item_id": ln.item_id,
                        "batch_code": ln.batch_code,
                        "requested_qty": ln.requested_qty,
                        "confirmed_qty": ln.confirmed_qty,
                    }
                    for ln in (doc.lines or [])
                ],
            },
            auto_commit=False,
        )

        return await self.get_with_lines(session, doc.id)

    # ------------------------------------------------------------------ #
    # 取消：标记为 CANCELED（不动库存）                                  #
    # ------------------------------------------------------------------ #
    async def cancel(
        self,
        session: AsyncSession,
        *,
        doc_id: int,
        user_id: Optional[int] = None,
    ) -> InternalOutboundDoc:
        """
        取消内部出库单：

        - 仅 DRAFT 状态可取消；
        - 不做库存回滚（因为还没扣库存）；
        - 写审计事件 INTERNAL_OUT_CANCELED。
        """
        doc = await self.get_with_lines(session, doc_id, for_update=True)

        if doc.status != "DRAFT":
            raise ValueError(f"内部出库单 {doc.id} 状态为 {doc.status}，不能取消")

        doc.status = "CANCELED"
        doc.canceled_by = user_id
        doc.canceled_at = datetime.now(UTC)

        await session.flush()

        await AuditEventWriter.write(
            session,
            flow="OUTBOUND",
            event="INTERNAL_OUT_CANCELED",
            ref=doc.doc_no,
            trace_id=doc.trace_id,
            meta={
                "doc_id": doc.id,
                "doc_no": doc.doc_no,
                "warehouse_id": doc.warehouse_id,
                "doc_type": doc.doc_type,
                "recipient_name": doc.recipient_name,
            },
            auto_commit=False,
        )

        return await self.get_with_lines(session, doc.id)
