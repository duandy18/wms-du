# app/api/routers/print_jobs.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import print_jobs_routes

router = APIRouter(prefix="/print-jobs", tags=["print-jobs"])


def _register_all_routes() -> None:
    print_jobs_routes.register(router)


_register_all_routes()

__all__ = ["router"]
