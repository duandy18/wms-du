from app.main import app

for r in app.routes:
    print(r.path, r.methods)
