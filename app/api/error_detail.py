# app/api/error_detail.py
from __future__ import annotations

from typing import Dict

from fastapi import HTTPException


def raise_422(code: str, message: str) -> None:
    raise HTTPException(status_code=422, detail={"code": code, "message": message})


def raise_409(code: str, message: str) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message})


def raise_500(code: str, message: str) -> None:
    raise HTTPException(status_code=500, detail={"code": code, "message": message})


def as_error_detail(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}
