from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditWriter
from app.core.tx import TxManager
from app.models.item_barcode import ItemBarcode
from app.services.barcode import BarcodeResolver
from app.services.scan_handlers.count_handler import handle_count
from app.services.scan_handlers.pick_handler import handle_pick
from app.services.scan_handlers.receive_handler import handle_receive
from app.utils.gs1 import parse_gs1

UTC = timezone.utc
AUDIT = AuditWriter()
_BARCODE_RESOLVER = BarcodeResolver()

# 只允许这三种 scan 模式（putaway 在 v2 中禁用）
ALLOWED_SCAN_MODES = {"receive", "pick", "count"}

# ---------------- token parsing ----------------
_TOKEN_MAP = {
    "ITM": "item_id",
    "ITEM": "item_id",
    "ITEM_ID": "item_id",
    "QTY": "qty",
    "B": "batch_code",
    "BATCH": "batch_code",
    "BATCH_CODE": "batch_code",
    "PD": "production_date",
    "MFG": "production_date",
    "EXP": "expiry_date",
    "EXPIRY": "expiry_date",
    "TLID": "task_line_id",
    "TASK_LINE_ID": "task_line_id",
    "WH": "warehouse_id",
    "WAREHOUSE": "warehouse_id",
    "WAREHOUSE_ID": "warehouse_id",
}
_TOKEN_RE = re.compile(r"([A-Za-z_]+)\s*:\s*([^\s]+)")


def _parse_tokens(s: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for m in _TOKEN_RE.finditer(s or ""):
        k = _TOKEN_MAP.get(m.group(1).upper())
        v = m.group(2)
        if not k:
            continue
        if k in {"item_id", "qty", "task_line_id", "warehouse_id"}:
            try:
                out[k] = int(v)
            except Exception:
                pass
        elif k in {"production_date", "expiry_date"}:
            out[k] = v
        else:
            out[k] = v
    return out


# ---------------- date helpers ----------------
def _coerce_date(v: Any) -> Optional[date]:
    """
    将各种输入类型统一转换为 date 对象。非法则返回 None，由下游校验。
    支持：date/datetime、'YYYY-MM-DD'、'YYYYMMDD'、数值 20260101。
    """
    if v is None:
        return None

    if isinstance(v, (int, float)):
        v = str(int(v))

    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s)
        except Exception:
            pass
        if len(s) == 8 and s.isdigit():
            try:
                return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
            except Exception:
                return None
    return None


def _date_to_json(v: Any) -> Optional[str]:
    """用于审计：把 date 转成 ISO 字符串，其他类型一律返回 None。"""
    if isinstance(v, date):
        return v.isoformat()
    return None


# ---------------- scan_ref ----------------
def _scan_ref(raw: Dict[str, Any]) -> str:
    """
    生成 scan_ref：
    - device_id 优先从 raw["device_id"] / ctx["device_id"]；
    - 否则 fallback 到 "dev"。
    """
    ctx = raw.get("ctx") or {}
    if not isinstance(ctx, dict):
        ctx = {}

    dev = raw.get("device_id") or ctx.get("device_id") or "dev"
    dev = str(dev).strip()

    tokens = raw.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}

    bc = str(raw.get("barcode") or tokens.get("barcode") or "").strip()
    ts = (raw.get("ts") or datetime.now(UTC).isoformat())[:16]
    return f"scan:{dev}:{ts}:{bc}"


async def _normalize_ref(
    session: AsyncSession,
    ref: str,
    *,
    table: str = "stock_ledger",
    column: str = "ref",
) -> str:
    """将 ref 截断到数据库列允许的最大长度"""
    try:
        q = SA(
            """
            SELECT character_maximum_length
              FROM information_schema.columns
             WHERE table_schema = 'public'
               AND table_name = :t
               AND column_name = :c
            """
        )
        row = await session.execute(q, {"t": table, "c": column})
        maxlen = row.scalar()
        if isinstance(maxlen, int) and maxlen > 0 and len(ref) > maxlen:
            return ref[:maxlen]
    except Exception:
        pass
    return ref


# ---------------- barcode → item_id 映射 ----------------
async def _resolve_item_id_from_barcode(
    session: AsyncSession,
    barcode: str,
) -> Optional[int]:
    code = (barcode or "").strip()
    if not code:
        return None

    stmt = (
        sa.select(ItemBarcode.item_id)
        .where(ItemBarcode.barcode == code)
        .order_by(ItemBarcode.active.desc(), ItemBarcode.id.asc())
    )

    try:
        row = await session.execute(stmt)
        item_id = row.scalar_one_or_none()
        if item_id is None:
            return None
        try:
            return int(item_id)
        except Exception:
            return None
    except Exception:
        return None


async def _resolve_item_id_from_sku(
    session: AsyncSession,
    sku: str,
) -> Optional[int]:
    s = (sku or "").strip()
    if not s:
        return None

    try:
        row = await session.execute(
            SA("SELECT id FROM items WHERE sku = :s LIMIT 1"),
            {"s": s},
        )
        item_id = row.scalar_one_or_none()
        if item_id is None:
            return None
        return int(item_id)
    except Exception:
        return None


# ---------------- master parse ----------------
async def _parse(
    scan: Dict[str, Any],
    session: AsyncSession,
) -> Tuple[
    Dict[str, Any],
    str,
    bool,
    int,
    int,
    Optional[str],
    int,
    Optional[date],
    Optional[date],
]:
    """
    统一解析 /scan 请求，返回：
      parsed, mode, probe, qty, item_id, batch_code, warehouse_id,
      production_date(date|None), expiry_date(date|None)
    """
    # 1) 从 barcode 字符串里解析 KV token：ITM: / QTY: / B: / PD: / EXP: / WH:
    raw = str(scan.get("barcode") or (scan.get("tokens") or {}).get("barcode") or "")
    parsed = _parse_tokens(raw)

    # 2) 用 ScanRequest 顶层字段“补洞”（显式字段优先）
    for f in (
        "item_id",
        "qty",
        "task_line_id",
        "batch_code",
        "warehouse_id",
        "production_date",
        "expiry_date",
    ):
        v_scan = scan.get(f)
        v_parsed = parsed.get(f)
        if (v_parsed is None or v_parsed == "") and v_scan is not None:
            parsed[f] = v_scan

    # 3) 使用 item_barcodes 反查 item_id
    if raw and parsed.get("item_id") is None:
        item_id_from_barcode = await _resolve_item_id_from_barcode(session, raw)
        if item_id_from_barcode:
            parsed["item_id"] = item_id_from_barcode

    # 4) 使用 BarcodeResolver（SKU / GTIN / 批次 / 到期）
    if raw:
        try:
            r = _BARCODE_RESOLVER.parse(raw)
        except Exception:
            r = None

        if r is not None:
            # SKU → item_id
            if getattr(r, "sku", None) and parsed.get("item_id") is None:
                iid = await _resolve_item_id_from_sku(
                    session,
                    r.sku,  # type: ignore[arg-type]
                )
                if iid:
                    parsed["item_id"] = iid

            # GTIN → item_id
            if getattr(r, "gtin", None) and parsed.get("item_id") is None:
                iid2 = await _resolve_item_id_from_barcode(
                    session,
                    r.gtin,  # type: ignore[arg-type]
                )
                if iid2:
                    parsed["item_id"] = iid2

            # 批次 / 到期
            if getattr(r, "batch", None) and not parsed.get("batch_code"):
                parsed["batch_code"] = r.batch  # type: ignore[assignment]
            if getattr(r, "expiry", None) and not parsed.get("expiry_date"):
                parsed["expiry_date"] = r.expiry  # type: ignore[assignment]

    # 5) 兜底：尝试 GS1 解析
    if raw and not (parsed.get("item_id") or parsed.get("batch_code") or parsed.get("expiry_date")):
        gs1 = parse_gs1(raw)
        if gs1:
            if "batch" in gs1 and "batch_code" not in parsed:
                parsed["batch_code"] = gs1["batch"]
            if "expiry" in gs1 and "expiry_date" not in parsed:
                parsed["expiry_date"] = gs1["expiry"]
            for k in ("item_id", "production_date", "expiry_date", "batch_code"):
                if gs1.get(k) and not parsed.get(k):
                    parsed[k] = gs1[k]

    mode = (scan.get("mode") or "count").lower()
    probe = bool(scan.get("probe"))
    qty = int(parsed.get("qty") or scan.get("qty") or 1)
    item_id = int(parsed.get("item_id") or 0)
    batch_code = parsed.get("batch_code")
    wh_id = int(parsed.get("warehouse_id") or scan.get("warehouse_id") or 1)

    production_date = _coerce_date(parsed.get("production_date"))
    expiry_date = _coerce_date(parsed.get("expiry_date"))

    return (
        parsed,
        mode,
        probe,
        qty,
        item_id,
        batch_code,
        wh_id,
        production_date,
        expiry_date,
    )


# ============================ Orchestrator ============================
async def ingest(scan: Dict[str, Any], session: Optional[AsyncSession]) -> Dict[str, Any]:
    """
    v2 扫描编排器（receive / pick / count，putaway 禁用）：
      - 解析 ScanRequest / barcode / GS1 / item_barcodes / BarcodeResolver
      - probe 模式：
          * receive / count：跑 handler，但不提交 Tx
          * pick：只做解析，不调用 handle_pick，不动账（条码→item_id 解析服务）
      - commit 模式：TxManager + 对应 handler
      - 统一返回结构（ok/committed/scan_ref/event_id/evidence/errors）
    """
    if session is None:
        dummy = _scan_ref(scan)
        return {
            "ok": False,
            "committed": False,
            "scan_ref": dummy,
            "event_id": None,
            "source": None,
            "evidence": [],
            "errors": [{"stage": "ingest", "error": "missing session"}],
            "item_id": None,
        }

    (
        parsed,
        mode,
        probe,
        qty,
        item_id,
        batch_code,
        wh_id,
        production_date,
        expiry_date,
    ) = await _parse(scan, session)

    scan_ref = await _normalize_ref(session, _scan_ref(scan))
    evidence: List[Dict[str, Any]] = []

    if mode not in ALLOWED_SCAN_MODES:
        ev = await AUDIT.other(session, scan_ref)
        return {
            "ok": False,
            "committed": False,
            "scan_ref": scan_ref,
            "event_id": ev,
            "source": "scan_feature_disabled",
            "evidence": [{"source": "scan_feature_disabled", "db": True}],
            "errors": [{"stage": "ingest", "error": "FEATURE_DISABLED: putaway"}],
            "item_id": item_id,
        }

    base_kwargs: Dict[str, Any] = {
        "item_id": item_id,
        "warehouse_id": wh_id,
        "batch_code": batch_code,
        "ref": scan_ref,
        "production_date": production_date,
        "expiry_date": expiry_date,
    }

    def get_audit_kwargs(kw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **kw,
            "production_date": _date_to_json(kw.get("production_date")),
            "expiry_date": _date_to_json(kw.get("expiry_date")),
        }

    try:
        # ---------------- count ----------------
        if mode == "count":
            kwargs = {
                **base_kwargs,
                "actual": qty,
                "trace_id": scan_ref,
            }
            audit_kwargs = get_audit_kwargs(kwargs)

            _ = await AUDIT.path(session, "count", {"dedup": scan_ref, "kw": audit_kwargs})
            evidence.append({"source": "scan_count_path", "db": True})

            count_payload: Dict[str, Any] | None = None
            try:
                result_obj = await TxManager.run(session, probe=probe, fn=handle_count, **kwargs)
                if isinstance(result_obj, dict):
                    count_payload = result_obj
            except Exception as ex:
                ev = await AUDIT.error(session, "count", scan_ref, str(ex))
                return {
                    "ok": False,
                    "committed": False,
                    "scan_ref": scan_ref,
                    "event_id": ev,
                    "source": "scan_count_error",
                    "evidence": evidence,
                    "errors": [{"stage": "count", "error": str(ex)}],
                    "item_id": item_id,
                }

            def enrich_with_count(payload: Dict[str, Any]) -> Dict[str, Any]:
                """
                将 handle_count 返回的 enriched 字段合并到 orchestrator payload 上：
                - actual / delta / before / after
                - warehouse_id / batch_code
                - production_date / expiry_date
                - item_id（若 handler 返回）
                """
                if not isinstance(count_payload, dict):
                    return payload

                # 1）数量相关
                actual_raw = count_payload.get("actual")
                delta_raw = count_payload.get("delta")

                try:
                    actual = int(actual_raw)
                    delta = int(delta_raw)
                except Exception:
                    # 尽量原样回显，别强行转型
                    if "actual" in count_payload:
                        payload["actual"] = actual_raw
                    if "delta" in count_payload:
                        payload["delta"] = delta_raw
                    return payload

                before = count_payload.get("before")
                after = count_payload.get("after")

                if before is None:
                    before = actual - delta
                if after is None:
                    after = actual

                wh_val = count_payload.get("warehouse_id", wh_id)

                payload["warehouse_id"] = wh_val
                payload["actual"] = actual
                payload["delta"] = delta
                payload["before"] = before
                payload["before_qty"] = before
                payload["after"] = after
                payload["after_qty"] = after

                # 2）批次 & 日期相关
                payload["batch_code"] = count_payload.get("batch_code") or batch_code

                # 这里保持原始 date 对象，由 FastAPI/Pydantic 负责 JSON 序列化
                prod = count_payload.get("production_date") or production_date
                exp = count_payload.get("expiry_date") or expiry_date
                if prod is not None:
                    payload["production_date"] = prod
                if exp is not None:
                    payload["expiry_date"] = exp

                # 3）顺带把 item_id 补一下（如果 handler 有返回）
                if count_payload.get("item_id"):
                    payload["item_id"] = count_payload["item_id"]

                return payload

            if probe:
                # probe：完整执行 handle_count，但不 commit Tx，用于调试 before/delta/after
                ev = await AUDIT.probe(session, "count", scan_ref)
                base = {
                    "ok": True,
                    "committed": False,
                    "scan_ref": scan_ref,
                    "event_id": ev,
                    "source": "scan_count_probe",
                    "evidence": evidence,
                    "errors": [],
                    "item_id": item_id,
                }
                return enrich_with_count(base)

            # commit：正常落账
            ev = await AUDIT.commit(session, "count", {"dedup": scan_ref})
            base = {
                "ok": True,
                "committed": True,
                "scan_ref": scan_ref,
                "event_id": ev,
                "source": "scan_count_commit",
                "evidence": evidence,
                "errors": [],
                "item_id": item_id,
            }
            return enrich_with_count(base)

        # ---------------- receive ----------------
        if mode == "receive":
            kwargs = {
                **base_kwargs,
                "qty": qty,
                "trace_id": scan_ref,
            }
            audit_kwargs = get_audit_kwargs(kwargs)

            _ = await AUDIT.path(session, "receive", {"dedup": scan_ref, "kw": audit_kwargs})
            evidence.append({"source": "scan_receive_path", "db": True})

            await TxManager.run(session, probe=probe, fn=handle_receive, **kwargs)

            if probe:
                ev = await AUDIT.probe(session, "receive", scan_ref)
                return {
                    "ok": True,
                    "committed": False,
                    "scan_ref": scan_ref,
                    "event_id": ev,
                    "source": "scan_receive_probe",
                    "evidence": evidence + [{"source": "scan_receive_probe", "db": True}],
                    "errors": [],
                    "item_id": item_id,
                }

            ev = await AUDIT.commit(session, "receive", {"dedup": scan_ref})
            return {
                "ok": True,
                "committed": True,
                "scan_ref": scan_ref,
                "event_id": ev,
                "source": "scan_receive_commit",
                "evidence": evidence + [{"source": "scan_receive_commit", "db": True}],
                "errors": [],
                "item_id": item_id,
            }

        # ---------------- pick ----------------
        # pick + probe：只做解析，不调用 handle_pick（不动账）
        if mode == "pick" and probe:
            parse_kwargs = {
                "item_id": item_id,
                "warehouse_id": wh_id,
                "batch_code": batch_code,
                "ref": scan_ref,
                "qty": qty,
                "task_line_id": parsed.get("task_line_id"),
                "trace_id": scan_ref,
                "production_date": production_date,
                "expiry_date": expiry_date,
            }
            audit_kwargs = get_audit_kwargs(parse_kwargs)

            _ = await AUDIT.path(session, "pick", {"dedup": scan_ref, "kw": audit_kwargs})
            evidence.append({"source": "scan_pick_path", "db": True})

            ev = await AUDIT.probe(session, "pick", scan_ref)
            return {
                "ok": True,
                "committed": False,
                "scan_ref": scan_ref,
                "event_id": ev,
                "source": "scan_pick_probe_parse_only",
                "evidence": evidence + [{"source": "scan_pick_probe", "db": True}],
                "errors": [],
                "item_id": item_id,
            }

        # pick + commit：真正写入拣货任务（不扣库存）
        kwargs = {
            "item_id": item_id,
            "warehouse_id": wh_id,
            "batch_code": batch_code,
            "ref": scan_ref,
            "qty": qty,
            "task_line_id": parsed.get("task_line_id"),
            "trace_id": scan_ref,
        }
        audit_kwargs = {
            **kwargs,
            "production_date": _date_to_json(production_date),
            "expiry_date": _date_to_json(expiry_date),
        }

        _ = await AUDIT.path(session, "pick", {"dedup": scan_ref, "kw": audit_kwargs})
        evidence.append({"source": "scan_pick_path", "db": True})

        await TxManager.run(session, probe=probe, fn=handle_pick, **kwargs)

        if probe:
            ev = await AUDIT.probe(session, "pick", scan_ref)
            return {
                "ok": True,
                "committed": False,
                "scan_ref": scan_ref,
                "event_id": ev,
                "source": "scan_pick_probe",
                "evidence": evidence + [{"source": "scan_pick_probe", "db": True}],
                "errors": [],
                "item_id": item_id,
            }

        ev = await AUDIT.commit(session, "pick", {"dedup": scan_ref})
        return {
            "ok": True,
            "committed": True,
            "scan_ref": scan_ref,
            "event_id": ev,
            "source": "scan_pick_commit",
            "evidence": evidence + [{"source": "scan_pick_commit", "db": True}],
            "errors": [],
            "item_id": item_id,
        }

    except Exception as e:
        ev = await AUDIT.error(session, mode, scan_ref, str(e))
        return {
            "ok": False,
            "committed": False,
            "scan_ref": scan_ref,
            "event_id": ev,
            "source": f"scan_{mode}_error",
            "evidence": evidence,
            "errors": [{"stage": mode, "error": str(e)}],
            "item_id": item_id,
        }
