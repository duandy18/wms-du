from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session
from app.wms.inventory_adjustment.count.contracts.count_doc import (
    CountDocCreateIn,
    CountDocDetailOut,
    CountDocFreezeOut,
    CountDocLinesUpdateIn,
    CountDocLinesUpdateOut,
    CountDocListOut,
    CountDocOut,
    CountDocPostOut,
)
from app.wms.inventory_adjustment.count.services.count_doc_service import CountDocService

router = APIRouter(
    prefix="/inventory-adjustment/count-docs",
    tags=["inventory-adjustment-count-docs"],
)


@router.post("", response_model=CountDocOut, status_code=status.HTTP_201_CREATED)
async def create_count_doc(
    payload: CountDocCreateIn,
    session: AsyncSession = Depends(get_async_session),
) -> CountDocOut:
    service = CountDocService()
    try:
        out = await service.create_doc(
            session,
            payload=payload,
            actor_user_id=None,  # 当前阶段先不接 user runtime；created_by 允许为空
        )
        await session.commit()
        return out
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"create_count_doc_failed: {e}") from e


@router.get("", response_model=CountDocListOut, status_code=status.HTTP_200_OK)
async def list_count_docs(
    warehouse_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_async_session),
) -> CountDocListOut:
    service = CountDocService()
    try:
        return await service.list_docs(
            session,
            warehouse_id=warehouse_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"list_count_docs_failed: {e}") from e


@router.get("/{doc_id}", response_model=CountDocDetailOut, status_code=status.HTTP_200_OK)
async def get_count_doc_detail(
    doc_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> CountDocDetailOut:
    service = CountDocService()
    try:
        return await service.get_doc_detail(session, doc_id=int(doc_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"get_count_doc_detail_failed: {e}") from e


@router.post("/{doc_id}/freeze", response_model=CountDocFreezeOut, status_code=status.HTTP_200_OK)
async def freeze_count_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> CountDocFreezeOut:
    service = CountDocService()
    try:
        out = await service.freeze_doc(session, doc_id=int(doc_id))
        await session.commit()
        return out
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"freeze_count_doc_failed: {e}") from e


@router.put("/{doc_id}/lines", response_model=CountDocLinesUpdateOut, status_code=status.HTTP_200_OK)
async def update_count_doc_lines(
    doc_id: int,
    payload: CountDocLinesUpdateIn,
    session: AsyncSession = Depends(get_async_session),
) -> CountDocLinesUpdateOut:
    service = CountDocService()
    try:
        out = await service.update_doc_lines(
            session,
            doc_id=int(doc_id),
            payload=payload,
        )
        await session.commit()
        return out
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"update_count_doc_lines_failed: {e}") from e


@router.post("/{doc_id}/post", response_model=CountDocPostOut, status_code=status.HTTP_200_OK)
async def post_count_doc(
    doc_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> CountDocPostOut:
    service = CountDocService()
    try:
        out = await service.post_doc(
            session,
            doc_id=int(doc_id),
        )
        await session.commit()
        return out
    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"post_count_doc_failed: {e}") from e
