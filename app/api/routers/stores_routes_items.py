# app/api/routers/stores_routes_items.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.api.routers.stores_routes_bindings_helpers import check_store_perm, ensure_store_exists
from app.api.routers.stores_schemas import (
    StoreItemsListOut,
    StoreItemRow,
    StoreItemAddIn,
    StoreItemAddOut,
    StoreItemDeleteOut,
)
from app.db.deps import get_db


def register(router: APIRouter) -> None:
    @router.get("/stores/{store_id}/items", response_model=StoreItemsListOut)
    async def list_store_items(
        store_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        店铺卖哪些 SKU（store_items）。
        权限：config.store.read
        """
        check_store_perm(db, current_user, ["config.store.read"])
        await ensure_store_exists(session, store_id)

        sql = text(
            """
            SELECT
              si.item_id,
              i.name AS item_name
            FROM store_items AS si
            JOIN items AS i ON i.id = si.item_id
            WHERE si.store_id = :sid
            ORDER BY si.item_id ASC
            """
        )
        rows = (await session.execute(sql, {"sid": int(store_id)})).mappings().all()

        data = [
            StoreItemRow(
                item_id=int(r["item_id"]),
                item_name=r.get("item_name"),
            )
            for r in rows
        ]
        return StoreItemsListOut(ok=True, data=data)

    @router.post("/stores/{store_id}/items", response_model=StoreItemAddOut)
    async def add_store_item(
        store_id: int = Path(..., ge=1),
        payload: StoreItemAddIn = ...,
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        将 SKU 加入店铺（写 store_items）。
        权限：config.store.write

        强约束：
        - item 必须存在
        - (store_id, item_id) 已存在则 409（让操作者明确“已经加入过”）
        """
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        # 1) item 必须存在
        row_item = (
            await session.execute(
                text("SELECT id FROM items WHERE id=:iid LIMIT 1"),
                {"iid": int(payload.item_id)},
            )
        ).first()
        if not row_item:
            raise HTTPException(status_code=404, detail="item not found")

        # 2) 已存在则 409
        existed = (
            await session.execute(
                text(
                    """
                    SELECT 1
                      FROM store_items
                     WHERE store_id=:sid
                       AND item_id=:iid
                     LIMIT 1
                    """
                ),
                {"sid": int(store_id), "iid": int(payload.item_id)},
            )
        ).first()
        if existed:
            raise HTTPException(status_code=409, detail="store item already exists")

        # 3) 插入
        try:
            await session.execute(
                text(
                    """
                    INSERT INTO store_items (store_id, item_id)
                    VALUES (:sid, :iid)
                    """
                ),
                {"sid": int(store_id), "iid": int(payload.item_id)},
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

        return StoreItemAddOut(ok=True, data={"store_id": int(store_id), "item_id": int(payload.item_id)})

    @router.delete("/stores/{store_id}/items/{item_id}", response_model=StoreItemDeleteOut)
    async def delete_store_item(
        store_id: int = Path(..., ge=1),
        item_id: int = Path(..., ge=1),
        session: AsyncSession = Depends(get_session),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        从店铺移除 SKU（删 store_items）。
        权限：config.store.write
        """
        check_store_perm(db, current_user, ["config.store.write"])
        await ensure_store_exists(session, store_id)

        sql = text(
            """
            DELETE FROM store_items
             WHERE store_id=:sid
               AND item_id=:iid
            RETURNING id
            """
        )
        res = await session.execute(sql, {"sid": int(store_id), "iid": int(item_id)})
        row = res.first()
        await session.commit()

        if not row:
            raise HTTPException(status_code=404, detail="store item not found")

        return StoreItemDeleteOut(ok=True, data={"store_id": int(store_id), "item_id": int(item_id)})
