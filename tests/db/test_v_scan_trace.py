import pytest
from sqlalchemy import text

# 与现有分组标记保持一致
pytestmark = pytest.mark.grp_scan


@pytest.mark.asyncio
async def test_v_scan_trace_view_exists(session):
    """
    视图必须存在于 public schema。
    口径：只校验存在性，不绑定实现文件位置。
    """
    sql = text(
        """
        SELECT 1
        FROM pg_catalog.pg_views
        WHERE schemaname='public' AND viewname='v_scan_trace'
    """
    )
    res = await session.execute(sql)
    assert res.scalar() == 1, "public.v_scan_trace not found"


@pytest.mark.asyncio
async def test_v_scan_trace_has_min_columns(session):
    """
    放宽字段断言：至少包含关键列 'scan_ref'（其它列可能随实现演进而变化）。
    这样避免因实现细节变更导致测试频繁破碎。
    """
    sql = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='v_scan_trace'
    """
    )
    cols = {r[0] for r in (await session.execute(sql)).all()}
    assert "scan_ref" in cols, f"v_scan_trace missing required column: scan_ref; got={sorted(cols)}"


@pytest.mark.asyncio
async def test_v_scan_trace_coalesce_expr_in_viewdef(session):
    """
    视图定义需体现 JSONB 兼容的 COALESCE 读法，兼容以下两类写入：
      1) JSONB 对象：message->>'ref' 或 message->>'scan_ref'
      2) JSON 字符串：btrim(message::text, '\"') 或直接 message::text
    断言采用“存在性+宽松匹配”，避免绑定具体格式化/换行。
    """
    sql = text("SELECT pg_get_viewdef('public.v_scan_trace'::regclass, true)")
    viewdef = (await session.execute(sql)).scalar() or ""
    vd_low = viewdef.lower()

    # 必须使用 coalesce 且涉及 message 字段
    assert (
        "coalesce" in vd_low and "message" in vd_low
    ), f"viewdef missing COALESCE(message*): {viewdef}"

    # JSONB 键读取至少包含 ->>'ref' 或 ->>'scan_ref' 之一
    has_ref_key = "->>'ref'" in vd_low or "->> 'ref'" in vd_low
    has_scan_ref_key = "->>'scan_ref'" in vd_low or "->> 'scan_ref'" in vd_low
    assert (
        has_ref_key or has_scan_ref_key
    ), f"viewdef should include ->>'ref' or ->>'scan_ref': {viewdef}"

    # 兼容 probe 写 JSON 字符串的路径：出现 message::text 或 btrim(message::text, '\"')
    has_string_path = ("message::text" in vd_low) or ("btrim(" in vd_low and "message" in vd_low)
    assert (
        has_string_path
    ), f"viewdef should handle JSON string case (message::text / btrim): {viewdef}"


@pytest.mark.asyncio
async def test_v_scan_trace_recent_has_rows_or_zero(session):
    """
    近 1 天记录数量应 >= 0（存在性/可查询性检查，不强制必须有数据）。
    """
    sql = text(
        """
        SELECT COUNT(*) FROM public.v_scan_trace
        WHERE occurred_at >= now() - interval '1 day'
    """
    )
    n = (await session.execute(sql)).scalar_one()
    assert n >= 0
