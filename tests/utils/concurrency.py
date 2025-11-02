import asyncio

async def run_concurrently(n, coro_factory):
    tasks = [asyncio.create_task(coro_factory(i)) for i in range(n)]
    return await asyncio.gather(*tasks, return_exceptions=True)
