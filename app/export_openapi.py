# app/export_openapi.py
import importlib
import json

# Dynamic import: try app.main first, then project-root main.py
CANDIDATES = ["app.main", "main"]


def _load_app():
    for mod in CANDIDATES:
        try:
            m = importlib.import_module(mod)
        except Exception:
            continue
        if hasattr(m, "app"):
            return m.app
    raise RuntimeError(
        "FastAPI `app` not found in app.main or main; define `app = FastAPI()`."
    )


def main():
    app = _load_app()
    schema = app.openapi()
    print(json.dumps(schema, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
