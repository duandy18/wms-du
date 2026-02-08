# app/services/platform_sku_mirror_service.py
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


_WS_RE = re.compile(r"\s+")


def _norm_ws(s: Optional[str]) -> Optional[str]:
    """
    统一空白归一化：
    - strip
    - 多个空白合并为单空格
    """
    if s is None:
        return None
    if not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    return _WS_RE.sub(" ", t)


def _as_str_from_any(v: Any) -> Optional[str]:
    """
    更宽松：允许 int/float 转 str，用于某些平台把 name/spec 编成数字 id 的情况。
    """
    if v is None:
        return None
    if isinstance(v, str):
        return _norm_ws(v)
    if isinstance(v, (int, float)):
        return str(v)
    return None


def _maybe_parse_json_obj(raw_payload: Any) -> Optional[dict[str, Any]]:
    """
    raw_payload 在 ORM 层是 JSONB（通常是 dict），但历史/外部输入可能是 str。
    """
    if raw_payload is None:
        return None
    if isinstance(raw_payload, dict):
        return raw_payload
    if isinstance(raw_payload, str):
        try:
            obj = json.loads(raw_payload)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else None
    return None


def _pick_first(obj: dict[str, Any], keys: list[str]) -> Optional[str]:
    for k in keys:
        if k not in obj:
            continue
        s = _as_str_from_any(obj.get(k))
        if s:
            return s
    return None


def _extract_sku_name_spec_from_raw(raw_payload: Any) -> tuple[Optional[str], Optional[str]]:
    """
    平台“解析 SKU”的最小可推广实现：
    - 不绑定任何平台特定结构（先做通用候选字段）
    - 只抽取“可读线索”：sku_name / spec
    """
    obj = _maybe_parse_json_obj(raw_payload)
    if not obj:
        return None, None

    name_keys = [
        "sku_name",
        "skuName",
        "name",
        "title",
        "goods_name",
        "goodsName",
        "product_name",
        "productName",
        "item_name",
        "itemName",
    ]

    spec_keys = [
        "spec",
        "spec_name",
        "specName",
        "variant",
        "variant_name",
        "variantName",
        "sku_spec",
        "skuSpec",
        "specification",
        "specification_name",
    ]

    sku_name = _pick_first(obj, name_keys)
    spec = _pick_first(obj, spec_keys)

    if spec is None:
        attrs = obj.get("attributes") or obj.get("props") or obj.get("properties")
        if isinstance(attrs, dict):
            parts: list[str] = []
            for k, v in attrs.items():
                kk = _as_str_from_any(k)
                vv = _as_str_from_any(v)
                if kk and vv:
                    parts.append(f"{kk}:{vv}")
            if parts:
                spec = " ".join(parts)
        elif isinstance(attrs, list):
            parts2: list[str] = []
            for it in attrs:
                if not isinstance(it, dict):
                    continue
                kk = _as_str_from_any(it.get("name") or it.get("key"))
                vv = _as_str_from_any(it.get("value"))
                if kk and vv:
                    parts2.append(f"{kk}:{vv}")
            if parts2:
                spec = " ".join(parts2)

    return sku_name, spec


class PlatformSkuMirrorService:
    """
    ✅ 平台同步唯一写入口：platform_sku_mirror

    工程约束（硬红线）：
    - 只允许写 mirror（UPSERT by (platform, store_id, platform_sku_id)）
    - 允许覆盖字段：
        sku_name / spec / raw_payload / source / observed_at
    - 严禁在此处改写：
        platform_sku_bindings / FSKU / Item
    """

    def __init__(self, db: Session):
        self.db = db

    def upsert(
        self,
        *,
        platform: str,
        store_id: int,
        platform_sku_id: str,
        sku_name: Optional[str],
        spec: Optional[str],
        raw_payload: Optional[dict[str, Any]],
        source: str,
        observed_at: datetime,
    ) -> None:
        sku_name_clean = _norm_ws(sku_name)
        spec_clean = _norm_ws(spec)

        if (sku_name_clean is None) or (spec_clean is None):
            rn, rs = _extract_sku_name_spec_from_raw(raw_payload)
            if sku_name_clean is None and rn is not None:
                sku_name_clean = _norm_ws(rn)
            if spec_clean is None and rs is not None:
                spec_clean = _norm_ws(rs)

        self.db.execute(
            text(
                """
                insert into platform_sku_mirror(
                  platform, store_id, platform_sku_id,
                  sku_name, spec, raw_payload, source, observed_at,
                  created_at, updated_at
                ) values (
                  :platform, :store_id, :platform_sku_id,
                  :sku_name, :spec, (:raw_payload)::jsonb, :source, :observed_at,
                  now(), now()
                )
                on conflict (platform, store_id, platform_sku_id)
                do update set
                  sku_name     = excluded.sku_name,
                  spec         = excluded.spec,
                  raw_payload  = excluded.raw_payload,
                  source       = excluded.source,
                  observed_at  = excluded.observed_at,
                  updated_at   = now();
                """
            ),
            {
                "platform": platform,
                "store_id": store_id,
                "platform_sku_id": platform_sku_id,
                "sku_name": sku_name_clean,
                "spec": spec_clean,
                "raw_payload": None if raw_payload is None else json.dumps(raw_payload, ensure_ascii=False),
                "source": source,
                "observed_at": observed_at,
            },
        )
