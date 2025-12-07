# app/api/routes/pdd_auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.pdd_auth_service import PddAuthError, PddAuthService

router = APIRouter(prefix="/pdd", tags=["pdd-auth"])


@router.get("/auth/url")
async def get_pdd_auth_url(
    store_id: int = Query(..., description="内部 stores.id"),
    db: AsyncSession = Depends(get_session),
):
    """
    前端调用这个接口，拿到 PDD 授权 URL，然后 window.location.href 跳过去。
    """
    service = PddAuthService(db)
    try:
        url = await service.build_auth_url(store_id=store_id)
    except PddAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"authorize_url": url}


@router.get("/oauth/callback", response_class=HTMLResponse)
async def pdd_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_session),
):
    """
    被拼多多回调的入口：?code=xxx&state=yyy

    正常场景下，处理完后你可以给一个简单 HTML 提示“授权成功，可以关闭窗口”。
    """
    service = PddAuthService(db)
    try:
        token_row, store_id = await service.handle_callback(code=code, state=state)
    except PddAuthError as exc:
        # 这里直接给 HTML，不然用户看到一堆 JSON 会懵
        return HTMLResponse(
            f"<h3>PDD 授权失败</h3><p>{exc}</p>",
            status_code=400,
        )

    # 最小可用：简单 HTML 提示
    html = f"""
    <html>
      <head><title>PDD 授权成功</title></head>
      <body>
        <h3>授权成功</h3>
        <p>店铺已绑定到内部 Store ID: {store_id}</p>
        <p>可以关闭本窗口，回到 WMS-DU。</p>
      </body>
    </html>
    """
    return HTMLResponse(html)
