# app/services/pick_task_service.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.pick_task import PickTask
from app.models.pick_task_line import PickTaskLine
from app.services.order_service import OrderService
from app.services.pick_service import PickService
from app.services.soft_reserve_service import SoftReserveService

UTC = timezone.utc


# ========================= 数据结构：commit 行 & 差异 =========================


@dataclass
class PickTaskCommitLine:
    item_id: int
    req_qty: int
    picked_qty: int
    warehouse_id: int
    batch_code: Optional[str]
    order_id: Optional[int] = None


@dataclass
class PickTaskDiffLine:
    """
    差异按 item_id 汇总：

    - req_qty    : 该 item 的总计划量（仅统计来自订单的行，即 order_id 非空）
    - picked_qty : 该 item 的总拣货量（所有行 picked 之和）
    - delta      : picked_qty - req_qty
    - status:
        "OK"     : picked == req
        "UNDER"  : picked <  req
        "OVER"   : picked >  req
    """

    item_id: int
    req_qty: int
    picked_qty: int
    delta: int
    status: str


@dataclass
class PickTaskDiffSummary:
    task_id: int
    lines: List[PickTaskDiffLine]
    has_over: bool
    has_under: bool


class PickTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- 内部工具 ---------------- #

    async def _load_task(
        self,
        task_id: int,
        *,
        for_update: bool = False,
    ) -> PickTask:
        stmt = select(PickTask).options(selectinload(PickTask.lines)).where(PickTask.id == task_id)
        if for_update:
            stmt = stmt.with_for_update()

        res = await self.session.execute(stmt)
        task = res.scalars().first()
        if task is None:
            raise ValueError(f"PickTask not found: id={task_id}")
        if task.lines:
            task.lines.sort(key=lambda line: (line.id,))
        return task

    async def _load_order_head(
        self,
        order_id: int,
    ) -> Optional[Dict[str, Any]]:
        row = (
            (
                await self.session.execute(
                    SA(
                        """
                    SELECT
                        id,
                        platform,
                        shop_id,
                        ext_order_no,
                        warehouse_id,
                        trace_id
                      FROM orders
                     WHERE id = :oid
                     LIMIT 1
                    """
                    ),
                    {"oid": order_id},
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    async def _load_order_items(
        self,
        order_id: int,
    ) -> List[Dict[str, Any]]:
        rows = (
            (
                await self.session.execute(
                    SA(
                        """
                    SELECT
                        id,
                        item_id,
                        COALESCE(qty, 0) AS qty
                      FROM order_items
                     WHERE order_id = :oid
                     ORDER BY id ASC
                    """
                    ),
                    {"oid": order_id},
                )
            )
            .mappings()
            .all()
        )

        return [
            {
                "order_line_id": int(r["id"]),
                "item_id": int(r["item_id"]),
                "qty": int(r["qty"] or 0),
            }
            for r in rows
        ]

    # ---------------- 从订单创建拣货任务 ---------------- #

    async def create_for_order(
        self,
        *,
        order_id: int,
        warehouse_id: Optional[int] = None,
        source: str = "ORDER",
        priority: int = 100,
    ) -> PickTask:
        """
        从订单创建拣货任务：

        - 必须先保证订单有 warehouse_id（或调用方显式指定 warehouse_id）；
        - 同步构造/更新软预占：OrderService.reserve → OrderReserveFlow → SoftReserveService；
        - 再创建 pick_tasks + pick_task_lines。
        """
        order = await self._load_order_head(order_id)
        if not order:
            raise ValueError(f"Order not found: id={order_id}")

        platform = str(order["platform"]).upper()
        shop_id = str(order["shop_id"])
        ext_no = str(order["ext_order_no"])
        trace_id = order.get("trace_id")

        # 仓库决策：优先使用显式传入的 warehouse_id，其次订单上的 warehouse_id。
        order_wh = order.get("warehouse_id")
        if warehouse_id is not None:
            wh_id = int(warehouse_id)
        elif order_wh:
            wh_id = int(order_wh)
        else:
            # 不再偷偷 fallback=1，避免“假仓库”破坏 Golden Flow
            raise ValueError(
                f"Order {order_id} has no warehouse_id, cannot create pick task or soft reservation. "
                f"请先确保订单绑定仓库（/dev/orders/.../ensure-warehouse 或店铺默认仓绑定）。"
            )

        order_ref = f"ORD:{platform}:{shop_id}:{ext_no}"

        items = await self._load_order_items(order_id)
        if not items:
            raise ValueError(f"Order {order_id} has no items, cannot create pick task.")

        # ✅ 先走 Golden Flow：按订单构建软预占（Reservation v2）
        #    - 幂等：OrderReserveFlow/SoftReserveService 自己处理
        #    - 若库存不足，抛 ValueError，由上层返回 409/400
        await OrderService.reserve(
            session=self.session,
            platform=platform,
            shop_id=shop_id,
            ref=order_ref,
            lines=[{"item_id": r["item_id"], "qty": r["qty"]} for r in items],
            trace_id=trace_id,
        )

        # ✅ 再创建拣货任务 & 行项目
        now = datetime.now(UTC)

        task = PickTask(
            warehouse_id=wh_id,
            source=source,
            ref=order_ref,
            priority=priority,
            status="READY",
            assigned_to=None,
            note=None,
            created_at=now,
            updated_at=now,
        )

        self.session.add(task)
        await self.session.flush()  # 拿到 task.id

        for row in items:
            if row["qty"] <= 0:
                continue
            line = PickTaskLine(
                task_id=task.id,
                order_id=order_id,
                order_line_id=row["order_line_id"],
                item_id=row["item_id"],
                req_qty=row["qty"],
                picked_qty=0,
                batch_code=None,
                prefer_pickface=True,
                target_location_id=None,
                status="OPEN",
                note=None,
                created_at=now,
                updated_at=now,
            )
            self.session.add(line)

        await self.session.flush()
        return await self._load_task(task.id)

    # ---------------- 扫码拣货（只更新任务，不动库存） ---------------- #

    async def record_scan(
        self,
        *,
        task_id: int,
        item_id: int,
        qty: int,
        batch_code: Optional[str],
    ) -> PickTask:
        """
        扫码拣货：只更新拣货任务行（req_qty / picked_qty / batch_code），
        不直接动库存。库存扣减统一在 commit_ship 中通过 PickService 完成。
        """
        if qty == 0:
            return await self._load_task(task_id)

        task = await self._load_task(task_id, for_update=True)

        if task.status not in ("READY", "ASSIGNED", "PICKING"):
            raise ValueError(f"PickTask {task.id} status={task.status} cannot accept pick scan.")

        norm_batch = (batch_code or "").strip() or None

        target: Optional[PickTaskLine] = None
        for line in task.lines or []:
            if line.item_id == item_id and ((line.batch_code or None) == norm_batch):
                target = line
                break

        now = datetime.now(UTC)

        if target is None:
            # 新增一行“临时计划”+实际拣货
            target = PickTaskLine(
                task_id=task.id,
                order_id=None,
                order_line_id=None,
                item_id=item_id,
                req_qty=int(qty),  # 首拣数量作为“临时计划”，仅供本行使用
                picked_qty=int(qty),
                batch_code=norm_batch,
                prefer_pickface=False,
                target_location_id=None,
                status="OPEN",
                note=None,
                created_at=now,
                updated_at=now,
            )
            self.session.add(target)
            await self.session.flush()
            task.lines.append(target)
        else:
            if not target.batch_code and norm_batch:
                target.batch_code = norm_batch
            target.picked_qty = int(target.picked_qty or 0) + int(qty)
            target.updated_at = now

        if task.status in ("READY", "ASSIGNED"):
            task.status = "PICKING"
        task.updated_at = now

        await self.session.flush()
        return task

    # ---------------- commit 视图 ---------------- #

    async def get_commit_lines(
        self,
        *,
        task_id: int,
        ignore_zero: bool = True,
    ) -> Tuple[PickTask, List[PickTaskCommitLine]]:
        task = await self._load_task(task_id)
        lines: List[PickTaskCommitLine] = []

        for line in task.lines or []:
            picked = int(line.picked_qty or 0)
            req = int(line.req_qty or 0)
            if ignore_zero and picked <= 0:
                continue

            lines.append(
                PickTaskCommitLine(
                    item_id=int(line.item_id),
                    req_qty=req,
                    picked_qty=picked,
                    warehouse_id=int(task.warehouse_id),
                    batch_code=(line.batch_code or None),
                    order_id=int(line.order_id) if line.order_id is not None else None,
                )
            )

        return task, lines

    # ---------------- 差异分析：按 item 汇总（只统计“有订单”的 req_qty） ---------------- #

    async def compute_diff(
        self,
        *,
        task_id: int,
    ) -> PickTaskDiffSummary:
        """
        按 item_id 汇总差异：

        - req_qty 总量只统计 order_id 非空的行（来自订单的计划）；
        - picked_qty 总量统计所有行（包括临时拣货行）。
        """
        task, commit_lines = await self.get_commit_lines(task_id=task_id, ignore_zero=False)

        agg: Dict[int, Dict[str, int]] = {}
        for line in commit_lines:
            state = agg.setdefault(line.item_id, {"req": 0, "picked": 0})

            # 计划量只看有 order_id 的行（来自订单）
            if line.order_id is not None:
                state["req"] += int(line.req_qty)

            # 实际拣货量：所有行都算
            state["picked"] += int(line.picked_qty)

        diff_lines: List[PickTaskDiffLine] = []
        has_over = False
        has_under = False

        for item_id, state in agg.items():
            req_total = state["req"]
            picked_total = state["picked"]
            delta = picked_total - req_total

            if delta == 0:
                status = "OK"
            elif delta < 0:
                status = "UNDER"
                has_under = True
            else:
                status = "OVER"
                has_over = True

            diff_lines.append(
                PickTaskDiffLine(
                    item_id=item_id,
                    req_qty=req_total,
                    picked_qty=picked_total,
                    delta=delta,
                    status=status,
                )
            )

        return PickTaskDiffSummary(
            task_id=task_id,
            lines=diff_lines,
            has_over=has_over,
            has_under=has_under,
        )

    # ---------------- commit 出库（Golden Flow：PICK + 消耗软预占） ---------------- #

    async def commit_ship(
        self,
        *,
        task_id: int,
        platform: str,
        shop_id: str,
        trace_id: Optional[str] = None,
        allow_diff: bool = True,
    ) -> Dict[str, Any]:
        """
        拣货任务提交（Golden Flow 版）：

        - 不再直接 StockService.adjust(reason=SHIP) 硬出库；
        - 改为：
            1) 通过 PickService.record_pick 扣减库存（MovementType.PICK）；
            2) 通过 SoftReserveService.pick_consume 消耗该订单 ref 的软预占；
            3) 写 outbound_commits_v2 标记“出库提交完成”；
            4) 标记任务及明细为 DONE。

        - 仅当 ref 是 ORD:{PLAT}:{shop_id}:ext_order_no 且来源为 ORDER 时，
          才会尝试消耗软预占；否则只视为“非订单任务”的扣库操作。
        """
        task = await self._load_task(task_id, for_update=True)

        # 差异分析（按 item 汇总，req 只看订单行）
        diff_summary = await self.compute_diff(task_id=task.id)

        if not allow_diff and (diff_summary.has_over or diff_summary.has_under):
            raise ValueError(
                f"PickTask {task.id} has diff (OVER/UNDER), commit is not allowed in strict mode."
            )

        task, commit_lines = await self.get_commit_lines(task_id=task.id, ignore_zero=True)

        if not commit_lines:
            raise ValueError(f"PickTask {task.id} has no picked_qty > 0, cannot commit.")

        plat = platform.upper()
        shop = str(shop_id)
        wh_id = int(task.warehouse_id)
        order_ref = str(task.ref or f"PICKTASK:{task.id}")
        occurred_at = datetime.now(UTC)

        pick_svc = PickService()
        soft_reserve = SoftReserveService()

        # 聚合 per (item_id, batch_code) 扣库存
        from typing import Tuple as _Tuple  # 避免和上面 type hints 混淆
        agg: Dict[_Tuple[int, Optional[str]], int] = {}
        for line in commit_lines:
            key = (line.item_id, (line.batch_code or None))
            agg[key] = agg.get(key, 0) + line.picked_qty

        ref_line = 1

        # 1) 拣货扣库（PICK）
        for (item_id, batch_code), total_picked in agg.items():
            if total_picked <= 0:
                continue
            if not batch_code:
                raise ValueError(
                    f"PickTask {task.id} has picked_qty for item={item_id} "
                    f"but missing batch_code; cannot commit safely."
                )

            result = await pick_svc.record_pick(
                session=self.session,
                item_id=item_id,
                qty=total_picked,
                ref=order_ref,
                occurred_at=occurred_at,
                batch_code=batch_code,
                warehouse_id=wh_id,
                trace_id=trace_id,
                start_ref_line=ref_line,
            )
            ref_line = int(result.get("ref_line", ref_line)) + 1

        # 2) Golden Flow：仅对“订单来源的任务”消耗软预占
        if task.source == "ORDER" and order_ref.startswith(f"ORD:{plat}:{shop}:"):
            await soft_reserve.pick_consume(
                session=self.session,
                platform=plat,
                shop_id=shop,
                warehouse_id=wh_id,
                ref=order_ref,
                occurred_at=occurred_at,
                trace_id=trace_id,
            )

        # 3) 写 outbound_commits_v2，标记 ref 出库完成（逻辑口径）
        eff_trace_id = trace_id or order_ref
        await self.session.execute(
            SA(
                """
                INSERT INTO outbound_commits_v2 (
                    platform,
                    shop_id,
                    ref,
                    state,
                    created_at,
                    updated_at,
                    trace_id
                )
                VALUES (
                    :platform,
                    :shop_id,
                    :ref,
                    'COMPLETED',
                    now(),
                    now(),
                    :trace_id
                )
                ON CONFLICT (platform, shop_id, ref) DO NOTHING
                """
            ),
            {
                "platform": plat,
                "shop_id": shop,
                "ref": order_ref,
                "trace_id": eff_trace_id,
            },
        )

        # 4) 标记任务 DONE
        now = datetime.now(UTC)
        task.status = "DONE"
        task.updated_at = now
        for line in task.lines or []:
            line.status = "DONE"
            line.updated_at = now

        await self.session.flush()

        return {
            "status": "OK",
            "task_id": task.id,
            "warehouse_id": wh_id,
            "platform": plat,
            "shop_id": shop,
            "ref": order_ref,
            "diff": {
                "task_id": diff_summary.task_id,
                "has_over": diff_summary.has_over,
                "has_under": diff_summary.has_under,
                "lines": [asdict(x) for x in diff_summary.lines],
            },
        }

    # ---------------- 仅标记任务完成（不扣库存） ---------------- #

    async def mark_done(
        self,
        *,
        task_id: int,
        note: Optional[str] = None,
    ) -> PickTask:
        task = await self._load_task(task_id, for_update=True)
        now = datetime.now(UTC)

        task.status = "DONE"
        task.updated_at = now
        if note:
            task.note = (task.note or "") + f"\n{note}"

        for line in task.lines or []:
            line.status = "DONE"
            line.updated_at = now

        await self.session.flush()
        return task
