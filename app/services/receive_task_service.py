# app/services/receive_task_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.models.receive_task import ReceiveTask, ReceiveTaskLine
from app.schemas.receive_task import OrderReturnLineIn
from app.services.inbound_service import InboundService
from app.services.order_event_bus import OrderEventBus
from app.services.order_reconcile_service import OrderReconcileService

UTC = timezone.utc


class ReceiveTaskService:
    """
    收货任务服务：

    - create_for_po: 从采购单创建收货任务（expected 来自剩余未收数量）；
    - create_for_order: 从订单创建收货任务（客户退货，expected 由调用方传入 + 上限校验）；
    - get_with_lines: 获取任务（头 + 行）；
    - record_scan: 在任务上累积扫码数量（只改 scanned_qty，不动库存，同时记录批次/日期）；
    - commit: 根据任务行的最终数量写入 ledger + stocks，并更新任务 / 采购单状态。

    重要约束（与 Cockpit UI 保持一致）：
    ------------------------------------------------
    - 任何 scanned_qty != 0 的行，在 commit 前必须满足：
        * 有 batch_code（非空字符串）
        * 且至少有 production_date 或 expiry_date 之一
      否则直接抛错，阻止 commit。
    """

    def __init__(self, inbound_svc: Optional[InboundService] = None) -> None:
        self.inbound_svc = inbound_svc or InboundService()

    # ------------ 工具：加载采购单 + 行 ------------ #

    async def _load_po(
        self,
        session: AsyncSession,
        po_id: int,
    ) -> PurchaseOrder:
        stmt = (
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.lines))
            .where(PurchaseOrder.id == po_id)
        )
        res = await session.execute(stmt)
        po = res.scalars().first()
        if po is None:
            raise ValueError(f"PurchaseOrder not found: id={po_id}")
        if po.lines:
            po.lines.sort(key=lambda line: (line.line_no, line.id))
        return po

    # ------------ 工具：订单数量 & 已退数量 & 已发数量（RMA 上限校验用） ------------ #

    async def _load_order_item_qty_map(
        self,
        session: AsyncSession,
        order_id: int,
    ) -> dict[int, int]:
        rows = await session.execute(
            text(
                """
                SELECT item_id, COALESCE(qty, 0) AS qty
                  FROM order_items
                 WHERE order_id = :oid
                """
            ),
            {"oid": order_id},
        )
        result: dict[int, int] = {}
        for item_id, qty in rows:
            result[int(item_id)] = int(qty or 0)
        return result

    async def _load_order_returned_qty_map(
        self,
        session: AsyncSession,
        order_id: int,
    ) -> dict[int, int]:
        rows = await session.execute(
            text(
                """
                SELECT
                    rtl.item_id,
                    SUM(
                        COALESCE(
                            CASE
                                WHEN rt.status = 'COMMITTED' THEN rtl.committed_qty
                                ELSE COALESCE(rtl.expected_qty, rtl.scanned_qty)
                            END,
                            0
                        )
                    ) AS returned_qty
                  FROM receive_task_lines AS rtl
                  JOIN receive_tasks AS rt
                    ON rt.id = rtl.task_id
                 WHERE rt.source_type = 'ORDER'
                   AND rt.source_id = :oid
                 GROUP BY rtl.item_id
                """
            ),
            {"oid": order_id},
        )
        result: dict[int, int] = {}
        for item_id, qty in rows:
            result[int(item_id)] = int(qty or 0)
        return result

    async def _load_order_shipped_qty_map(
        self,
        session: AsyncSession,
        order_id: int,
    ) -> dict[int, int]:
        head_row = (
            await session.execute(
                text(
                    """
                    SELECT platform, shop_id, ext_order_no
                      FROM orders
                     WHERE id = :oid
                     LIMIT 1
                    """
                ),
                {"oid": order_id},
            )
        ).first()
        if not head_row:
            return {}

        platform, shop_id, ext_order_no = head_row
        plat = str(platform or "").upper()
        shop = str(shop_id or "")
        ext_no = str(ext_order_no or "")
        order_ref = f"ORD:{plat}:{shop}:{ext_no}"

        rows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT
                        item_id,
                        SUM(
                            CASE WHEN delta < 0 THEN -delta ELSE 0 END
                        ) AS shipped_qty
                      FROM stock_ledger
                     WHERE ref = :ref
                     GROUP BY item_id
                    """
                    ),
                    {"ref": order_ref},
                )
            )
            .mappings()
            .all()
        )

        result: dict[int, int] = {}
        for r in rows:
            result[int(r["item_id"])] = int(r.get("shipped_qty") or 0)
        return result

    # ------------ 从采购单创建收货任务（供应商收货） ------------ #

    async def create_for_po(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        warehouse_id: Optional[int] = None,
        include_fully_received: bool = False,
    ) -> ReceiveTask:
        """
        从采购单创建收货任务（供应商收货）：

        - 对每一行，expected_qty = qty_ordered - qty_received（剩余未收）；
        - 若 include_fully_received=False，则跳过剩余<=0的行；
        - 同时复制采购行的静态信息（item_sku/spec/uom/...）到行快照；
        """
        po = await self._load_po(session, po_id)

        wh_id = warehouse_id or po.warehouse_id

        task = ReceiveTask(
            source_type="PO",
            source_id=po.id,
            po_id=po.id,
            supplier_id=po.supplier_id,
            supplier_name=po.supplier_name or po.supplier,
            warehouse_id=wh_id,
            status="DRAFT",
            remark=f"from PO-{po.id}",
        )
        session.add(task)
        await session.flush()

        lines_to_create: list[ReceiveTaskLine] = []
        for line in po.lines or []:
            remaining = line.qty_ordered - line.qty_received
            if remaining <= 0 and not include_fully_received:
                continue

            rtl = ReceiveTaskLine(
                task_id=task.id,
                po_line_id=line.id,
                item_id=line.item_id,
                item_name=line.item_name,
                item_sku=line.item_sku,
                category=line.category,
                spec_text=line.spec_text,
                base_uom=line.base_uom,
                purchase_uom=line.purchase_uom,
                units_per_case=line.units_per_case,
                batch_code=None,
                production_date=None,
                expiry_date=None,
                expected_qty=remaining if remaining > 0 else 0,
                scanned_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
            lines_to_create.append(rtl)

        if not lines_to_create:
            raise ValueError(f"采购单 {po.id} 已无剩余可收数量，无法创建收货任务")

        for rtl in lines_to_create:
            session.add(rtl)

        await session.flush()
        return await self.get_with_lines(session, task.id)

    # ------------ 从订单创建收货任务（客户退货 / RMA 入库） ------------ #

    async def create_for_order(
        self,
        session: AsyncSession,
        *,
        order_id: int,
        warehouse_id: Optional[int],
        lines: Sequence[OrderReturnLineIn],
    ) -> ReceiveTask:
        """
        从订单创建收货任务（客户退货入库 / RMA）：
        - v1：expected_qty 由调用方传入；
        - v2：增加“不可超过 min(ordered, shipped) - returned”的硬校验。
        """
        if not lines:
            raise ValueError("退货行不能为空")

        order_qty_map = await self._load_order_item_qty_map(session, order_id)
        returned_qty_map = await self._load_order_returned_qty_map(session, order_id)
        shipped_qty_map = await self._load_order_shipped_qty_map(session, order_id)

        for rc in lines:
            orig = int(order_qty_map.get(rc.item_id, 0))
            shipped = int(shipped_qty_map.get(rc.item_id, 0))
            already = int(returned_qty_map.get(rc.item_id, 0))
            cap = max(min(orig, shipped) - already, 0)

            if orig <= 0:
                raise ValueError(
                    f"订单 {order_id} 中不存在或未记录 item_id={rc.item_id} 的原始数量，"
                    f"无法为该商品创建退货任务"
                )
            if shipped <= 0:
                raise ValueError(
                    f"订单 {order_id} 的商品 item_id={rc.item_id} 尚未发货（shipped=0），"
                    f"不能创建退货任务"
                )
            if rc.qty > cap:
                raise ValueError(
                    f"订单 {order_id} 的商品 item_id={rc.item_id} 退货数量超出可退上限："
                    f"原始数量={orig}，已发货={shipped}，已退={already}，"
                    f"本次请求={rc.qty}，剩余可退={cap}"
                )

        wh_id = warehouse_id or 1

        task = ReceiveTask(
            source_type="ORDER",
            source_id=order_id,
            po_id=None,
            supplier_id=None,
            supplier_name=None,
            warehouse_id=wh_id,
            status="DRAFT",
            remark=f"return from ORDER-{order_id}",
        )
        session.add(task)
        await session.flush()

        created_lines: list[ReceiveTaskLine] = []
        for rc in lines:
            if rc.qty <= 0:
                continue
            created_lines.append(
                ReceiveTaskLine(
                    task_id=task.id,
                    po_line_id=None,
                    item_id=rc.item_id,
                    item_name=rc.item_name,
                    item_sku=None,
                    category=None,
                    spec_text=None,
                    base_uom=None,
                    purchase_uom=None,
                    units_per_case=None,
                    batch_code=rc.batch_code,
                    production_date=None,
                    expiry_date=None,
                    expected_qty=rc.qty,
                    scanned_qty=0,
                    committed_qty=None,
                    status="DRAFT",
                )
            )

        if not created_lines:
            raise ValueError("退货行数量必须大于 0")

        for rtl in created_lines:
            session.add(rtl)

        await session.flush()
        return await self.get_with_lines(session, task.id)

    # ------------ 查询任务 ------------ #

    async def get_with_lines(
        self,
        session: AsyncSession,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> ReceiveTask:
        stmt = (
            select(ReceiveTask)
            .options(selectinload(ReceiveTask.lines))
            .where(ReceiveTask.id == task_id)
        )
        if for_update:
            stmt = stmt.with_for_update()

        res = await session.execute(stmt)
        task = res.scalars().first()
        if task is None:
            raise ValueError(f"ReceiveTask not found: id={task_id}")

        if task.lines:
            task.lines.sort(key=lambda line: (line.id,))
        return task

    # ------------ 在任务上累积扫码 / 实收 ------------ #

    async def record_scan(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
    ) -> ReceiveTask:
        """
        对某一任务记录一次实收（扫码/录入）：

        - 只更新 ReceiveTaskLine.scanned_qty，不调用 inbound/stock；
        - qty 可正可负，允许回退，qty=0 表示“只更新元数据”（批次/日期）；
        - 若找不到对应 item_id 的行，则新建一行（expected_qty=None，纯实收）；
        - 同时记录/更新批次与批次日期信息。
        """
        task = await self.get_with_lines(session, task_id, for_update=True)
        if task.status != "DRAFT":
            raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能再修改")

        target: Optional[ReceiveTaskLine] = None
        for line in task.lines or []:
            if line.item_id == item_id:
                target = line
                break

        # 若不存在行，创建一条“仅实收”的行
        if target is None:
            target = ReceiveTaskLine(
                task_id=task.id,
                po_line_id=None,
                item_id=item_id,
                item_name=None,
                item_sku=None,
                category=None,
                spec_text=None,
                base_uom=None,
                purchase_uom=None,
                units_per_case=None,
                batch_code=batch_code,
                production_date=production_date,
                expiry_date=expiry_date,
                expected_qty=None,
                scanned_qty=0,
                committed_qty=None,
                status="DRAFT",
            )
            session.add(target)
            await session.flush()
        else:
            # 更新批次信息（若本次请求提供）
            if batch_code is not None:
                target.batch_code = batch_code
            if production_date is not None:
                target.production_date = production_date
            if expiry_date is not None:
                target.expiry_date = expiry_date

        # qty != 0 时才调整 scanned_qty；qty == 0 只更新 metadata
        if qty != 0:
            target.scanned_qty += int(qty)

        if target.expected_qty is not None:
            if target.scanned_qty == target.expected_qty:
                target.status = "MATCHED"
            else:
                target.status = "MISMATCH"
        else:
            target.status = "DRAFT"

        await session.flush()
        return await self.get_with_lines(session, task.id)

    # ------------ commit：真正写 ledger + stocks ------------ #

    async def commit(
        self,
        session: AsyncSession,
        *,
        task_id: int,
        trace_id: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
    ) -> ReceiveTask:
        """
        将收货任务真正“入库”：

        - 对每一行：
            committed_qty = scanned_qty
            调用 InboundService.receive(item_id, committed_qty, ...) 写 ledger+stocks；
        - 任务及行状态 → COMMITTED；
        - 如有 po_line_id，可同步更新采购单行的 qty_received/status。

        额外强约束（与 Cockpit/UI 保持一致）：
        - 任何 scanned_qty != 0 的行，在 commit 前必须具备：
            * 非空 batch_code
            * 至少一个日期（production_date 或 expiry_date）
        """
        task = await self.get_with_lines(session, task_id, for_update=True)
        if task.status != "DRAFT":
            raise ValueError(f"任务 {task.id} 状态为 {task.status}，不能重复 commit")

        if not task.lines:
            raise ValueError(f"任务 {task.id} 没有任何行，不能 commit")

        # ★ 服务端硬校验：任何有实收数量的行必须有批次 + 日期
        bad_line: Optional[ReceiveTaskLine] = None
        for line in task.lines:
            if not line.scanned_qty or line.scanned_qty == 0:
                continue
            no_batch = not line.batch_code or not str(line.batch_code).strip()
            no_dates = line.production_date is None and line.expiry_date is None
            if no_batch or no_dates:
                bad_line = line
                break

        if bad_line is not None:
            item_label = bad_line.item_name or f"item_id={bad_line.item_id}"
            raise ValueError(
                f"收货任务 {task.id} 中的行（{item_label}）已存在实收数量，但批次或生产/到期日期信息不完整，"
                f"请先补齐 batch_code 以及 production_date / expiry_date 后再提交。"
            )

        now = occurred_at or datetime.now(UTC)

        # ref 前缀根据来源区分：PO 收货 vs 订单退货入库
        if task.source_type == "ORDER":
            src_id = task.source_id or 0
            ref = f"RMA-{src_id or task.id}"
        else:
            ref = f"RT-{task.id}"

        # 准备 po_line 映射，方便更新采购单收货进度（仅 PO 模式使用）
        po_lines_map: dict[int, PurchaseOrderLine] = {}
        if task.po_id is not None:
            po = await self._load_po(session, task.po_id)
            for line in po.lines or []:
                po_lines_map[line.id] = line

        ref_line_counter = 0
        returned_by_item: dict[int, int] = {}

        for line in task.lines:
            if line.scanned_qty == 0:
                line.committed_qty = 0
                line.status = "COMMITTED"
                continue

            commit_qty = line.scanned_qty
            line.committed_qty = commit_qty

            ref_line_counter += 1

            await self.inbound_svc.receive(
                session=session,
                qty=commit_qty,
                ref=ref,
                ref_line=ref_line_counter,
                warehouse_id=task.warehouse_id,
                item_id=line.item_id,
                batch_code=line.batch_code,
                occurred_at=now,
                production_date=line.production_date,
                expiry_date=line.expiry_date,
                trace_id=trace_id,
            )

            line.status = "COMMITTED"

            # 若是 PO 源头，则更新采购单行收货数
            if line.po_line_id is not None and line.po_line_id in po_lines_map:
                po_line = po_lines_map[line.po_line_id]
                po_line.qty_received += commit_qty

            # 若是订单退货，则累加本次退货数量（用于 ORDER_RETURNED 事件）
            if task.source_type == "ORDER":
                returned_by_item[line.item_id] = returned_by_item.get(line.item_id, 0) + commit_qty

        task.status = "COMMITTED"
        await session.flush()

        # 若为订单退货，追加事件 + 更新订单对账
        if task.source_type == "ORDER" and task.source_id:
            order_id = int(task.source_id)
            try:
                row = (
                    await session.execute(
                        text(
                            """
                            SELECT platform, shop_id, ext_order_no
                              FROM orders
                             WHERE id = :oid
                             LIMIT 1
                            """
                        ),
                        {"oid": order_id},
                    )
                ).first()
                if row:
                    plat, shop_id, ext_no = row
                    order_ref = f"ORD:{str(plat).upper()}:{shop_id}:{ext_no}"
                else:
                    order_ref = ref

                await OrderEventBus.order_returned(
                    session,
                    ref=order_ref,
                    order_id=order_id,
                    warehouse_id=task.warehouse_id,
                    lines=[{"item_id": iid, "qty": qty} for iid, qty in returned_by_item.items()],
                    trace_id=trace_id,
                )

                recon = OrderReconcileService(session)
                result = await recon.reconcile_order(order_id)
                await recon.apply_counters(order_id)

                full_returned = all(
                    line_result.remaining_refundable == 0 for line_result in result.lines
                )
                new_status = "RETURNED" if full_returned else "PARTIALLY_RETURNED"

                await session.execute(
                    text(
                        """
                        UPDATE orders
                           SET status = :st,
                               updated_at = NOW()
                         WHERE id = :oid
                        """
                    ),
                    {"st": new_status, "oid": order_id},
                )

            except Exception:
                # 审计/对账失败不影响主流程
                pass

        return await self.get_with_lines(session, task.id)
