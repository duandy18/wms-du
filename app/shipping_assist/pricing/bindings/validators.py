# app/shipping_assist/pricing/bindings/validators.py
#
# 分拆说明：
# - 本文件从原 routes.py 中拆出 bindings 相关校验逻辑。
# - 目的：
#   1) 将“配置层绑定模板校验”和“运行层启用校验”分开
#   2) 避免 routes.py 同时承担路由与校验细节，降低维护复杂度
# - 维护约束：
#   - 绑定/换绑模板时，使用 _ensure_binding_template_allowed
#   - activate 时，使用 _ensure_activation_template_allowed
#   - 两者都不负责 SQL 写入，只负责合法性判断

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.shipping_assist.pricing.templates.module_resources_shared import (
    validate_template_ready_for_binding,
)
from app.shipping_assist.pricing.templates.repository import (
    build_template_stats,
    load_template_or_404,
)


async def _ensure_binding_template_allowed(
    session: AsyncSession,
    db: Session,
    *,
    shipping_provider_id: int,
    active_template_id: int | None,
) -> None:
    """
    绑定 / 换绑模板时使用的严格校验：

    - 模板必须存在、属于当前 provider
    - 模板不能 archived
    - 模板必须已验证通过、配置 ready
    - 模板不能已被任意 binding 占用
    """
    if active_template_id is None:
        return

    template = load_template_or_404(db, template_id=int(active_template_id))

    if int(template.shipping_provider_id) != int(shipping_provider_id):
        raise HTTPException(
            status_code=409,
            detail="pricing_template does not belong to shipping_provider",
        )

    if getattr(template, "archived_at", None) is not None or str(
        template.status or ""
    ) == "archived":
        raise HTTPException(status_code=409, detail="pricing_template archived")

    if str(template.validation_status) != "passed":
        raise HTTPException(status_code=409, detail="pricing_template not validated")

    stats = build_template_stats(db, template_id=int(active_template_id))

    if str(stats.config_status) != "ready":
        raise HTTPException(status_code=409, detail="pricing_template not ready")

    if int(stats.used_binding_count) != 0:
        raise HTTPException(
            status_code=409,
            detail="pricing_template already used by binding",
        )

    try:
        validate_template_ready_for_binding(db, template_id=int(active_template_id))
    except HTTPException as e:
        raise HTTPException(
            status_code=409, detail=f"pricing_template invalid: {e.detail}"
        ) from e


async def _ensure_activation_template_allowed(
    session: AsyncSession,
    db: Session,
    *,
    shipping_provider_id: int,
    active_template_id: int | None,
) -> None:
    """
    activate 时使用的轻校验：

    - 模板必须存在、属于当前 provider
    - 模板不能 archived
    - 模板必须已验证通过、配置 ready
    - 不校验 used_binding_count（因为当前 binding 自己重新启用是合法的）
    """
    if active_template_id is None:
        return

    template = load_template_or_404(db, template_id=int(active_template_id))

    if int(template.shipping_provider_id) != int(shipping_provider_id):
        raise HTTPException(
            status_code=409,
            detail="pricing_template does not belong to shipping_provider",
        )

    if getattr(template, "archived_at", None) is not None or str(
        template.status or ""
    ) == "archived":
        raise HTTPException(status_code=409, detail="pricing_template archived")

    if str(template.validation_status) != "passed":
        raise HTTPException(status_code=409, detail="pricing_template not validated")

    stats = build_template_stats(db, template_id=int(active_template_id))
    if str(stats.config_status) != "ready":
        raise HTTPException(status_code=409, detail="pricing_template not ready")

    try:
        validate_template_ready_for_binding(db, template_id=int(active_template_id))
    except HTTPException as e:
        raise HTTPException(
            status_code=409, detail=f"pricing_template invalid: {e.detail}"
        ) from e
