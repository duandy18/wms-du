# app/services/fulfillment_strategy_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Literal


@dataclass(frozen=True)
class StrategyContext:
    order_amount: Optional[float] = None
    sla_tier: Optional[str] = None
    # 未来可扩展：历史均价 / 失败率等（由调用方提供，策略层不查库）


@dataclass(frozen=True)
class CandidateFact:
    warehouse_id: int
    result: Literal["OK", "REJECTED"]
    reason: Optional[str] = None
    evidence: Dict[str, Any] = None


@dataclass(frozen=True)
class StrategyRecommendation:
    warehouse_id: Optional[int]
    reasons: List[str]


@dataclass(frozen=True)
class StrategyResult:
    ranked_candidates: List[int]
    recommendation: StrategyRecommendation
    strategy_tags: List[str]


class FulfillmentStrategyEngine(Protocol):
    def run(
        self,
        *,
        candidates: Sequence[int],
        facts: Sequence[CandidateFact],
        context: StrategyContext,
    ) -> StrategyResult: ...


class MinimalStrategyEngine:
    """
    v1：不引入配置系统，只做最小集：
    - 推荐 = candidates 中第一个 result=OK 的仓
    - 标签先空（后续再加 SLA/COST/STABLE）
    """
    def run(
        self,
        *,
        candidates: Sequence[int],
        facts: Sequence[CandidateFact],
        context: StrategyContext,
    ) -> StrategyResult:
        ok = {f.warehouse_id for f in facts if f.result == "OK"}
        ranked = [int(x) for x in candidates]  # v1 不重排
        rec = next((wid for wid in ranked if wid in ok), None)
        reasons = ["FIRST_OK_IN_CANDIDATES"] if rec is not None else ["NO_OK_CANDIDATE"]
        return StrategyResult(
            ranked_candidates=ranked,
            recommendation=StrategyRecommendation(warehouse_id=rec, reasons=reasons),
            strategy_tags=[],
        )
