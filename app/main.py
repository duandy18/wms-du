from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # 新增：导入 CORS 中间件

from app.api import auth, inventory, items, locations, orders, parties
from app.routers import users

app = FastAPI(
    title="WMS-DU API",
    version="v1",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

# 新增：添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法 (GET, POST, PUT, DELETE, etc)
    allow_headers=["*"],  # 允许所有头部
)

# 挂载所有路由
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(parties.router, prefix="/parties", tags=["Parties"])
app.include_router(locations.router, prefix="/locations", tags=["Locations"])
app.include_router(items.router, prefix="/items", tags=["Items"])
app.include_router(inventory.router, prefix="/inventory", tags=["Inventory"])
app.include_router(orders.router, prefix="/orders", tags=["Orders"])


@app.get("/ping")
def ping():
    return {"ok": True}
