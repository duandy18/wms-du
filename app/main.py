# app/main.py
from fastapi import FastAPI

app = FastAPI(title="WMS-DU API", version="v1")

# Optional: include routers if available
try:
    from . import routers as _routers

    if hasattr(_routers, "router"):
        app.include_router(_routers.router)
except Exception:
    # Routers not ready yet; skip
    pass


@app.get("/ping")
def ping():
    return {"ok": True}
