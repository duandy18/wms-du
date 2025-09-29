# apps/api/main.py
from fastapi import FastAPI

from app.routers import users  # your users router: app/routers/users.py

app = FastAPI(title="WMS-DU API")

# mount users router
app.include_router(users.router, prefix="/users", tags=["users"])


# health check (for CI/monitoring)
@app.get("/healthz")
def healthz():
    return {"status": "ok"}
