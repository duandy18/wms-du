import os

import pytest
import psycopg2
from dotenv import load_dotenv

# If running in CI with SQLite (default DATABASE_URL=sqlite:///test.db), skip the whole module
if os.getenv("DATABASE_URL", "").startswith("sqlite"):
    pytest.skip("skip db_core tests on SQLite CI", allow_module_level=True)

# 1. Load .env file
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

try:
    # 2. Connect to database
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )

    # 3. Run simple SQL
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print("✅ Success: connected to database, version:", version[0])

    # 4. Cleanup
    cur.close()
    conn.close()

except Exception as e:
    print("❌ Failed to connect to database:", e)
