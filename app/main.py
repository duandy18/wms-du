from fastapi import FastAPI

from app.api import (
    auth,
    inventory,
    items,
    locations,
    orders,  # 新增：导入 orders 路由
    parties,
)

# 导入所有需要的路由
from app.routers import users

app = FastAPI(
    title="WMS-DU API",
    version="v1",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

# 挂载所有路由
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(parties.router, prefix="/parties", tags=["Parties"])
app.include_router(locations.router, prefix="/locations", tags=["Locations"])
app.include_router(items.router, prefix="/items", tags=["Items"])
app.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])  # 新增：挂载 orders 路由


@app.get("/ping")
def ping():
    return {"ok": True}
