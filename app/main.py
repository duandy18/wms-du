# app/main.py
from fastapi import FastAPI

from app.routers import users
from app.routers import diag  # 新增的演示路由

app = FastAPI(
    title="WMS-DU API",
    version="v1",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

# ---- Mount routers ----
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(diag.router)  # /diag/secure

# ---- Health check ----
@app.get("/ping")
def ping():
    return {"ok": True}
