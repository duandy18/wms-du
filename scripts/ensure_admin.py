# scripts/ensure_admin.py
from __future__ import annotations

import os
import sys

from sqlalchemy import text

from app.core.security import get_password_hash
from app.db.session import async_session_maker


async def ensure_admin(
    username: str,
    password: str,
    *,
    full_name: str | None = None,
) -> None:
    hashed = get_password_hash(password)

    async with async_session_maker() as session:  # type: AsyncSession
        await session.execute(
            text(
                """
                INSERT INTO users (username, password_hash, is_active, primary_role_id, full_name, phone, email)
                VALUES (
                  :username,
                  :password_hash,
                  TRUE,
                  NULL,
                  :full_name,
                  NULL,
                  NULL
                )
                ON CONFLICT (username) DO UPDATE
                  SET password_hash   = EXCLUDED.password_hash,
                      is_active       = TRUE,
                      primary_role_id = EXCLUDED.primary_role_id,
                      full_name       = EXCLUDED.full_name
                """
            ),
            {
                "username": username,
                "password_hash": hashed,
                "full_name": full_name or username,
            },
        )
        await session.commit()


async def main() -> None:
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD")
    full_name = os.getenv("ADMIN_FULL_NAME", "Administrator")

    if not password:
        print("ERROR: ADMIN_PASSWORD 未设置", file=sys.stderr)
        sys.exit(1)

    dsn = os.getenv("WMS_DATABASE_URL") or os.getenv("DATABASE_URL")
    print(f"[ensure_admin] DSN = {dsn}")
    print(f"[ensure_admin] username = {username}")

    await ensure_admin(username=username, password=password, full_name=full_name)
    print("[ensure_admin] done.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
