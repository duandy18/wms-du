import os
import pytest

# 如果 CI 下使用 SQLite（默认 DATABASE_URL=sqlite:///test.db），则跳过整个模块
if os.getenv("DATABASE_URL", "").startswith("sqlite"):
    pytest.skip("skip db_core tests on SQLite CI", allow_module_level=True)

import psycopg2
from dotenv import load_dotenv

# 1. 读取 .env 文件
load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

try:
    # 2. 建立数据库连接
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )

    # 3. 创建游标并执行 SQL
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print("✅ Success: connected to database, version:", version[0])

    # 4. 清理
    cur.close()
    conn.close()

except Exception as e:
    print("❌ Failed to connect to database:", e)
