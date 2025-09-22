from fastapi import FastAPI

app = FastAPI(title="WMS-DU API")

@app.get("/healthz")
def healthz():
    return {"ok": True}
