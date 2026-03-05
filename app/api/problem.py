# app/api/problem.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, TypedDict

from fastapi import HTTPException


class ProblemDetail(TypedDict, total=False):
    # 必填
    type: str  # validation|batch|diff|shortage|state|idempotency
    # 可选：用于行内定位
    path: str  # e.g. pick_lines[2]
    # 常用字段（按需）
    reason: str
    item_id: int
    sku_code: str
    batch_code: Optional[str]

    req_qty: int
    picked_qty: int
    missing_qty: int
    over_qty: int

    required_qty: int
    available_qty: int
    short_qty: int


class NextAction(TypedDict, total=False):
    action: str
    label: str


@dataclass(frozen=True)
class Problem:
    error_code: str
    message: str
    http_status: int
    context: Optional[Dict[str, Any]] = None
    details: Optional[List[ProblemDetail]] = None
    next_actions: Optional[List[NextAction]] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
            "http_status": int(self.http_status),
        }
        if self.context:
            out["context"] = self.context
        if self.details:
            out["details"] = self.details
        if self.next_actions:
            out["next_actions"] = self.next_actions
        if self.trace_id:
            out["trace_id"] = self.trace_id
        return out


def make_problem(
    *,
    status_code: int,
    error_code: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    details: Optional[Sequence[ProblemDetail]] = None,
    next_actions: Optional[Sequence[NextAction]] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    p = Problem(
        error_code=str(error_code),
        message=str(message),
        http_status=int(status_code),
        context=context,
        details=list(details) if details else None,
        next_actions=list(next_actions) if next_actions else None,
        trace_id=trace_id,
    )
    return p.to_dict()


def raise_problem(
    *,
    status_code: int,
    error_code: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    details: Optional[Sequence[ProblemDetail]] = None,
    next_actions: Optional[Sequence[NextAction]] = None,
    trace_id: Optional[str] = None,
) -> None:
    raise HTTPException(
        status_code=int(status_code),
        detail=make_problem(
            status_code=int(status_code),
            error_code=error_code,
            message=message,
            context=context,
            details=details,
            next_actions=next_actions,
            trace_id=trace_id,
        ),
    )


def raise_422(error_code: str, message: str, *, details: Optional[Sequence[ProblemDetail]] = None) -> None:
    raise_problem(status_code=422, error_code=error_code, message=message, details=details)


def raise_409(error_code: str, message: str, *, details: Optional[Sequence[ProblemDetail]] = None) -> None:
    raise_problem(status_code=409, error_code=error_code, message=message, details=details)


def raise_500(error_code: str, message: str, *, trace_id: Optional[str] = None) -> None:
    raise_problem(status_code=500, error_code=error_code, message=message, trace_id=trace_id)
