from sqlalchemy import text

from app.db.session import SessionLocal

s = SessionLocal()
print(s.execute(text("SELECT 1")).scalar_one())
s.close()
print("smoke ok")
