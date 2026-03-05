# app/services/item_test_set_service.py
from __future__ import annotations

import inspect
from typing import Any, List

from sqlalchemy import text

from app.models.item import Item


class ItemTestSetService:
    """
    Test Set（DEFAULT）成员关系服务：

    - 负责把 item_test_sets / item_test_set_items 的 membership 映射成 Item.is_test 投影字段
    - 不负责 Item 的 CRUD（由 ItemService 负责）

    兼容要求（重要）：
    - 旧 async guard 依赖：
      * ItemTestSetService.NotFound
      * await ts.assert_items_not_in_test_set(...)
    - 本服务同时支持 Sync Session 与 AsyncSession：
      * Sync：get_membership_map / attach_* / enable / disable
      * Async：assert_items_not_in_test_set（用于 guard）
    """

    # ---- backward-compatible exceptions (old callers rely on these names) ----
    class NotFound(ValueError):
        """测试集合不存在（兼容旧调用方 ItemTestSetService.NotFound）"""

    class InTestSet(ValueError):
        """商品属于测试集合（用于 guard 阻断）"""

    def __init__(self, db: Any) -> None:
        # db 可能是 Session 或 AsyncSession；本服务按方法区分 sync/async 使用
        self.db = db

    # ===========================
    # Sync helpers (Session)
    # ===========================
    def _load_test_set_id(self, *, set_code: str) -> int:
        code = (set_code or "").strip()
        if not code:
            raise ValueError("set_code 不能为空")

        row = (
            self.db.execute(
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
            .mappings()
            .first()
        )
        if not row or row.get("id") is None:
            # ✅ 用 NotFound（但它继承 ValueError，兼容旧 except ValueError）
            raise ItemTestSetService.NotFound(f"测试集合不存在：{code}")
        return int(row["id"])

    def get_membership_map(self, *, item_ids: List[int], set_code: str = "DEFAULT") -> dict[int, bool]:
        """
        Sync 版：用于 Item 列表/详情投影 is_test。
        """
        ids = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return {}

        sid = self._load_test_set_id(set_code=set_code)
        rows = (
            self.db.execute(
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
            .mappings()
            .all()
        )
        hit = {int(r["item_id"]) for r in rows if r.get("item_id") is not None}
        return {i: (i in hit) for i in ids}

    def attach_is_test_for_items(self, *, items: List[Item], set_code: str = "DEFAULT") -> List[Item]:
        if not items:
            return items
        m = self.get_membership_map(item_ids=[int(x.id) for x in items], set_code=set_code)
        for it in items:
            setattr(it, "is_test", bool(m.get(int(it.id), False)))
        return items

    def attach_is_test_for_item(self, *, item: Item | None, set_code: str = "DEFAULT") -> Item | None:
        if item is None:
            return None
        m = self.get_membership_map(item_ids=[int(item.id)], set_code=set_code)
        setattr(item, "is_test", bool(m.get(int(item.id), False)))
        return item

    def enable(self, *, item_id: int, set_code: str = "DEFAULT") -> None:
        sid = self._load_test_set_id(set_code=set_code)
        self.db.execute(
            text(
                """
                INSERT INTO item_test_set_items(set_id, item_id)
                VALUES (:sid, :iid)
                ON CONFLICT (set_id, item_id) DO NOTHING
                """
            ),
            {"sid": int(sid), "iid": int(item_id)},
        )

    def disable(self, *, item_id: int, set_code: str = "DEFAULT") -> None:
        sid = self._load_test_set_id(set_code=set_code)
        self.db.execute(
            text(
                """
                DELETE FROM item_test_set_items
                 WHERE set_id = :sid
                   AND item_id = :iid
                """
            ),
            {"sid": int(sid), "iid": int(item_id)},
        )

    # ===========================
    # Async helpers (AsyncSession)
    # ===========================
    async def _aexec_first(self, sql: str, params: dict) -> dict | None:
        res = self.db.execute(text(sql), params)
        if inspect.isawaitable(res):
            res = await res
        row = res.mappings().first()
        return dict(row) if row else None

    async def _aexec_all(self, sql: str, params: dict) -> list[dict]:
        res = self.db.execute(text(sql), params)
        if inspect.isawaitable(res):
            res = await res
        rows = res.mappings().all()
        return [dict(r) for r in rows]

    async def assert_items_not_in_test_set(self, *, item_ids: List[int], set_code: str = "DEFAULT") -> None:
        """
        Async 版：用于 async guard（test_shop_testset_guard_service 等）。

        规则：
        - set 不存在：raise ItemTestSetService.NotFound
        - 任意 item 在 set 中：raise ItemTestSetService.InTestSet
        """
        ids = sorted({int(x) for x in item_ids if x is not None})
        if not ids:
            return

        code = (set_code or "").strip()
        if not code:
            raise ValueError("set_code 不能为空")

        row = await self._aexec_first(
            """
            SELECT id
              FROM item_test_sets
             WHERE code = :code
             LIMIT 1
            """,
            {"code": code},
        )
        if not row or row.get("id") is None:
            raise ItemTestSetService.NotFound(f"测试集合不存在：{code}")
        sid = int(row["id"])

        rows = await self._aexec_all(
            """
            SELECT item_id
              FROM item_test_set_items
             WHERE set_id = :sid
               AND item_id = ANY(:ids)
            """,
            {"sid": sid, "ids": ids},
        )
        hit = {int(r["item_id"]) for r in rows if r.get("item_id") is not None}
        if hit:
            raise ItemTestSetService.InTestSet(f"items in test_set[{code}]: {sorted(hit)}")
