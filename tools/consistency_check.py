#!/usr/bin/env python3
import argparse
import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.tasks.consistency import check_and_optionally_fix

DATABASE_URL = os.getenv("DATABASE_URL")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto-fix", action="store_true")
    parser.add_argument("--no-dry-run", action="store_true")
    args = parser.parse_args()

    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        mismatches = await check_and_optionally_fix(
            session, auto_fix=args.auto_fix, dry_run=not args.no_dry_run
        )
        print(f"mismatches={mismatches}")


if __name__ == "__main__":
    asyncio.run(main())
