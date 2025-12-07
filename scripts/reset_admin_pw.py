# scripts/reset_admin_pw.py
from __future__ import annotations

import asyncio

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.session import async_session_maker
from app.models.user import User

NEW_PASSWORD = "admin123"


async def reset_admin_password(session: AsyncSession, new_password: str) -> None:
    hashed = get_password_hash(new_password)
    stmt = update(User).where(User.username == "admin").values(password_hash=hashed)
    await session.execute(stmt)
    await session.commit()
    print("Password for admin reset to", new_password)


async def main() -> None:
    async with async_session_maker() as session:
        await reset_admin_password(session, NEW_PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
