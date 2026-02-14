# app/services/item_test_set_service.py
from __future__ import annotations

from typing import Iterable, List, Sequence, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ItemTestSetService:
    """
    测试商品白名单（Test Set）查询与断言。

    - 不污染主数据：items 仍是唯一主商品表
    - 只提供“是否在集合内”的能力，用于调试/门禁护栏
    """

    class NotFound(Exception):
        def __init__(self, message: str):
            super().__init__(message)
            self.message = message

    class Conflict(Exception):
        def __init__(self, message: str, *, out_of_set_item_ids: List[int], set_code: str):
            super().__init__(message)
            self.message = message
            self.out_of_set_item_ids = out_of_set_item_ids
            self.set_code = set_code

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _load_set_id(self, *, set_code: str) -> int:
        code = (set_code or "").strip()
        if not code:
            raise self.NotFound("set_code 不能为空")

        row = (
            await self.session.execute(
                text(
                    """
                    SELECT id
                      FROM item_test_sets
                     WHERE code = :code
                     LIMIT 1
                    """
                ),
                {"code": code},
            )
        ).mappings().first()

        if not row or row.get("id") is None:
            raise self.NotFound(f"测试集合不存在：{code}")

        return int(row["id"])

    async def is_item_in_test_set(self, *, item_id: int, set_code: str = "DEFAULT") -> bool:
        sid = await self._load_set_id(set_code=set_code)
        row = (
            await self.session.execute(
                text(
                    """
                    SELECT 1
                      FROM item_test_set_items
                     WHERE set_id = :sid
                       AND item_id = :iid
                     LIMIT 1
                    """
                ),
                {"sid": int(sid), "iid": int(item_id)},
            )
        ).first()
        return row is not None

    async def assert_items_in_test_set(self, *, item_ids: Sequence[int], set_code: str = "DEFAULT") -> None:
        """
        断言：item_ids 必须全部在 set_code 集合中。
        """
        ids: List[int] = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return

        sid = await self._load_set_id(set_code=set_code)

        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT item_id
                      FROM item_test_set_items
                     WHERE set_id = :sid
                       AND item_id = ANY(:ids)
                    """
                ),
                {"sid": int(sid), "ids": ids},
            )
        ).mappings().all()

        ok_ids: Set[int] = {int(r["item_id"]) for r in rows if r.get("item_id") is not None}
        bad: List[int] = [i for i in ids if i not in ok_ids]
        if bad:
            raise self.Conflict(
                "调试域隔离护栏：存在非测试白名单商品，拒绝执行（避免触碰真实库存）",
                out_of_set_item_ids=bad,
                set_code=(set_code or "").strip() or "DEFAULT",
            )

    async def assert_items_not_in_test_set(self, *, item_ids: Sequence[int], set_code: str = "DEFAULT") -> None:
        """
        断言：item_ids 必须全部不在 set_code 集合中（用于：非 TEST 商铺禁止测试商品进入）。
        """
        ids: List[int] = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return

        sid = await self._load_set_id(set_code=set_code)

        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT item_id
                      FROM item_test_set_items
                     WHERE set_id = :sid
                       AND item_id = ANY(:ids)
                    """
                ),
                {"sid": int(sid), "ids": ids},
            )
        ).mappings().all()

        hit_ids: List[int] = sorted({int(r["item_id"]) for r in rows if r.get("item_id") is not None})
        if hit_ids:
            raise self.Conflict(
                "主线隔离护栏：非测试商铺不允许出现测试商品（Test Set items），请更换绑定/修复 FSKU 组件",
                out_of_set_item_ids=hit_ids,
                set_code=(set_code or "").strip() or "DEFAULT",
            )

    async def get_membership_map(self, *, item_ids: Iterable[int], set_code: str = "DEFAULT") -> dict[int, bool]:
        ids: List[int] = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return {}

        sid = await self._load_set_id(set_code=set_code)
        rows = (
            await self.session.execute(
                text(
                    """
                    SELECT item_id
                      FROM item_test_set_items
                     WHERE set_id = :sid
                       AND item_id = ANY(:ids)
                    """
                ),
                {"sid": int(sid), "ids": ids},
            )
        ).mappings().all()

        ok_ids: Set[int] = {int(r["item_id"]) for r in rows if r.get("item_id") is not None}
        return {i: (i in ok_ids) for i in ids}
