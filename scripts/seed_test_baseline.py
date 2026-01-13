# scripts/seed_test_baseline.py
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text

from scripts.ensure_admin import ensure_admin as ensure_admin_user


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_sql(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Fixture SQL not found: {path}")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def discover_permission_names() -> list[str]:
    app_dir = _repo_root() / "app"
    if not app_dir.exists():
        return ["system.user.manage"]

    pat = re.compile(r"""["']([a-z][a-z0-9_]*\.[a-z0-9_]+\.[a-z0-9_.]+)["']""")
    names: set[str] = set()

    for p in app_dir.rglob("*.py"):
        try:
            s = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in pat.finditer(s):
            v = (m.group(1) or "").strip()
            if not v or len(v) > 128:
                continue
            if v.count(".") < 2:
                continue
            if not re.fullmatch(r"[a-z0-9_.]+", v):
                continue
            names.add(v)

    names.add("system.user.manage")
    return sorted(names)


async def seed_in_conn(conn) -> None:
    """
    在已有连接/事务里执行 seed（pytest/conftest 调用）
    调用方保证已 TRUNCATE 干净，并且 SET search_path TO public
    """
    root = _repo_root()
    base_sql_path = root / "tests" / "fixtures" / "base_seed.sql"
    shipping_sql_path = root / "tests" / "fixtures" / "shipping_seed.sql"

    # 1) 主数据/库存基线
    await conn.execute(text(_load_sql(base_sql_path)))

    # 2) 运费域最小基线（让 quote/zone brackets 测试可跑）
    if shipping_sql_path.exists():
        await conn.execute(text(_load_sql(shipping_sql_path)))

    # 3) admin 用户（可登录）
    await ensure_admin_user(username="admin", password="admin123", full_name="Dev Admin")

    # 4) RBAC：admin 全权
    names = discover_permission_names()

    await conn.execute(
        text(
            """
            INSERT INTO permissions (name)
            SELECT x.name
            FROM (SELECT unnest(CAST(:names AS text[])) AS name) AS x
            ON CONFLICT (name) DO NOTHING
            """
        ),
        {"names": names},
    )

    role_id = (
        await conn.execute(
            text(
                """
                INSERT INTO roles (name, description)
                VALUES ('admin', 'TEST admin role')
                ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
                RETURNING id
                """
            )
        )
    ).scalar_one_or_none()
    if role_id is None:
        role_id = (await conn.execute(text("SELECT id FROM roles WHERE name='admin' LIMIT 1"))).scalar_one()
    role_id = int(role_id)

    await conn.execute(
        text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT :rid, p.id
            FROM permissions p
            ON CONFLICT DO NOTHING
            """
        ),
        {"rid": role_id},
    )

    user_id = (await conn.execute(text("SELECT id FROM users WHERE username='admin' LIMIT 1"))).scalar_one()
    await conn.execute(
        text(
            """
            INSERT INTO user_roles (user_id, role_id)
            VALUES (:uid, :rid)
            ON CONFLICT DO NOTHING
            """
        ),
        {"uid": int(user_id), "rid": role_id},
    )

    await conn.execute(
        text(
            """
            UPDATE users
               SET primary_role_id = :rid
             WHERE id = :uid
               AND primary_role_id IS NULL
            """
        ),
        {"uid": int(user_id), "rid": role_id},
    )


async def main() -> None:
    dsn = os.getenv("WMS_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("WMS_DATABASE_URL / DATABASE_URL 未设置，无法 seed")

    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(dsn, poolclass=NullPool, pool_pre_ping=False, future=True)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET search_path TO public"))
            await seed_in_conn(conn)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
