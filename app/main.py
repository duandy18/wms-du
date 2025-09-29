# app/main.py
from fastapi import FastAPI

from app.routers import (
    users,  # Ensure app/routers/users.py defines `router = APIRouter()``
)

app = FastAPI(
    title="WMS-DU API",
    version="v1",
    openapi_url="/openapi.json",
    docs_url="/docs",
)

# Mount routers after app creation
app.include_router(users.router, prefix="/users", tags=["users"])


@app.get("/ping")
def ping():
    return {"ok": True}
