# app/infra/sql_tap.py
from __future__ import annotations

import os
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.engine import Engine

SLOW_MS = float(os.getenv("SLOW_SQL_MS", "50"))


def install(engine: Engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        context._wms_t0 = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        t0 = getattr(context, "_wms_t0", None)
        if t0 is None:
            return
        dt_ms = (perf_counter() - t0) * 1000.0
        if dt_ms >= SLOW_MS:
            # 截断 statement，避免日志过长
            sql_preview = " ".join(str(statement).split())[:400]
            print({"evt": "slow_sql", "elapsed_ms": round(dt_ms, 2), "sql": sql_preview})
