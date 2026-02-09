# app/api/schemas/psku_governance.py
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class PskuGovernanceStatus(BaseModel):
    """
    治理状态（读侧事实，不由前端推断）：

    - BOUND：current 且绑定到 fsku_id（符合新规则）
    - UNBOUND：无 current / current 不指向 fsku（需治理）
    - LEGACY_ITEM_BOUND：current 存在但绑定目标为 item_id（历史遗留；需迁移到 FSKU）
    """

    status: Literal["BOUND", "UNBOUND", "LEGACY_ITEM_BOUND"]


class PskuGovernanceActionHint(BaseModel):
    """
    下一步行动提示（后端裁决，前端只展示/筛选）：

    - OK：已符合新规则，无需治理动作
    - BIND_FIRST：未绑定（需要首次绑定到 published FSKU）
    - MIGRATE_LEGACY：历史 item_id 绑定（需要迁移到 FSKU）

    required：前端执行该动作前，必须收集的参数名（不暴露后端变量名到 UI 文案中，但可用于表单引导）。
    """

    action: Literal["OK", "BIND_FIRST", "MIGRATE_LEGACY"]
    required: list[Literal["fsku_id", "binding_id", "to_fsku_id"]] = []


class PskuBindCtx(BaseModel):
    """
    BIND_FIRST 的辅助上下文：
    - suggest_q：给 UI 展示的建议搜索词（可由 sku_name/spec 组合）
    - suggest_fsku_query：给 FSKU picker 的默认查询（尽量短、命中率高）
    """

    suggest_q: str
    suggest_fsku_query: str


class PskuGovernanceItem(BaseModel):
    platform: str
    store_id: int
    store_name: Optional[str] = None

    platform_sku_id: str
    sku_name: Optional[str] = None
    spec: Optional[str] = None

    mirror_freshness: Literal["ok", "missing"] = "ok"

    # current binding（无论 legacy 还是 fsku，都应暴露 binding_id，便于 migrate）
    binding_id: Optional[int] = None

    # 若 current 指向 fsku，则补齐 fsku 摘要
    fsku_id: Optional[int] = None
    fsku_code: Optional[str] = None
    fsku_name: Optional[str] = None
    fsku_status: Optional[str] = None

    governance: PskuGovernanceStatus
    action_hint: PskuGovernanceActionHint

    # BIND_FIRST 才会有（其它为 null）
    bind_ctx: Optional[PskuBindCtx] = None

    # ✅ 暂不猜 items.sku 字段，先输出事实：fsku_components.item_id 集合
    component_item_ids: list[int] = []


class PskuGovernanceOut(BaseModel):
    items: list[PskuGovernanceItem]
    total: int
    limit: int
    offset: int
