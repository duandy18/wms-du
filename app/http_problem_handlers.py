# app/http_problem_handlers.py
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.problem import make_problem

logger = logging.getLogger("wmsdu")


def _new_trace_id() -> str:
    return f"t_{uuid.uuid4().hex[:12]}"


def _problem_from_http_exc(req: Request, exc: HTTPException) -> Dict[str, Any]:
    """
    统一将 HTTPException.detail 翻译为 Problem 形状（蓝皮书 v1）。
    兼容历史形态：
    - str
    - list（例如 RequestValidationError safe list）
    - {"code","message"}
    - {"error_code","message",...}（已是 Problem）
    """
    status_code = int(exc.status_code)
    trace_id = _new_trace_id()

    ctx: Dict[str, Any] = {
        "path": getattr(req.url, "path", ""),
        "method": req.method,
    }

    d = exc.detail

    # 1) 已是 Problem（优先原样补齐 http_status/trace_id/context）
    if isinstance(d, dict) and "error_code" in d and "message" in d:
        out = dict(d)
        out.setdefault("http_status", status_code)
        out.setdefault("trace_id", trace_id)
        if isinstance(out.get("context"), dict):
            merged = dict(ctx)
            merged.update(out["context"])
            out["context"] = merged
        else:
            out["context"] = ctx
        return out

    # 2) 旧形态：{code,message} → Problem
    if isinstance(d, dict) and "code" in d and "message" in d:
        return make_problem(
            status_code=status_code,
            error_code=str(d.get("code") or "HTTP_ERROR"),
            message=str(d.get("message") or "请求被拒绝"),
            context=ctx,
            trace_id=trace_id,
        )

    # 3) detail=list：当作 validation 详情
    if isinstance(d, list):
        details: List[Dict[str, Any]] = []
        for i, e in enumerate(d):
            if isinstance(e, dict):
                details.append(
                    {
                        "type": "validation",
                        "path": f"validation[{i}]",
                        "reason": str(e.get("msg") or e.get("type") or "invalid"),
                    }
                )
            else:
                details.append({"type": "validation", "path": f"validation[{i}]", "reason": str(e)})
        return make_problem(
            status_code=status_code,
            error_code="request_validation_error",
            message="请求参数不合法",
            context=ctx,
            details=details,
            trace_id=trace_id,
        )

    # 4) detail=str / 其它：兜底为 state
    msg = str(d) if d is not None else "请求被拒绝"
    return make_problem(
        status_code=status_code,
        error_code="http_error",
        message=msg,
        context=ctx,
        details=[{"type": "state", "reason": msg}],
        trace_id=trace_id,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def _unhandled_exc(req: Request, exc: Exception):
        trace_id = _new_trace_id()
        logger.exception("UNHANDLED_EXC[%s]: %s", trace_id, exc)
        content = make_problem(
            status_code=500,
            error_code="internal_error",
            message="系统异常，请稍后重试",
            context={"path": getattr(req.url, "path", ""), "method": req.method},
            trace_id=trace_id,
        )
        return JSONResponse(status_code=500, content=content)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(req: Request, exc: RequestValidationError):
        raw = exc.errors()
        details: List[Dict[str, Any]] = []
        for i, e in enumerate(raw):
            if not isinstance(e, dict):
                continue
            details.append(
                {
                    "type": "validation",
                    "path": f"validation[{i}]",
                    "reason": str(e.get("msg") or e.get("type") or "invalid"),
                }
            )

        content = make_problem(
            status_code=422,
            error_code="request_validation_error",
            message="请求参数不合法",
            context={"path": getattr(req.url, "path", ""), "method": req.method},
            details=details,
            trace_id=_new_trace_id(),
        )
        return JSONResponse(status_code=422, content=content)

    @app.exception_handler(HTTPException)
    async def _http_exc(req: Request, exc: HTTPException):
        content = _problem_from_http_exc(req, exc)
        return JSONResponse(status_code=int(exc.status_code), content=content)
