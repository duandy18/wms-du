from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

def uniq_ref(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"

async def ensure_store(session: AsyncSession, platform="__internal__", name="__NO_STORE__") -> int:
    await session.execute(
        text("INSERT INTO stores(platform,name) VALUES(:p,:n) ON CONFLICT DO NOTHING"),
        {"p": platform, "n": name},
    )
    row = await session.execute(
        text("SELECT id FROM stores WHERE platform=:p2 AND name=:n2 LIMIT 1"),
        {"p2": platform, "n2": name},
    )
    return int(row.scalar_one())
