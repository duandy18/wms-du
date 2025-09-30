import contextlib
import os

import pytest
from dotenv import load_dotenv


# 用装饰器声明式跳过：SQLite CI 下整类测试跳过
@pytest.mark.skipif(
    os.getenv("DATABASE_URL", "").startswith("sqlite"),
    reason="Skip DB tests on SQLite CI",
)
class TestDatabaseCore:
    @pytest.fixture(scope="class")
    def db_config(self):
        """Load DB configuration from env/.env (no hard-coded secrets)."""
        load_dotenv()
        return {
            "dbname": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASS"),
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
        }

    @pytest.fixture(scope="class")
    def db_connection(self, db_config):
        """
        Provide a DB connection for all tests in this class.
        Open once; close after class tests finish.
        """
        # 仅在需要时按需获取 psycopg2；缺包则跳过（不会在模块导入时失败）
        psycopg2 = pytest.importorskip("psycopg2")

        conn = None
        try:
            conn = psycopg2.connect(
                dbname=db_config["dbname"],
                user=db_config["user"],
                password=db_config["password"],
                host=db_config["host"],
                port=db_config["port"],
            )
            yield conn
        except psycopg2.OperationalError as e:
            pytest.fail(f"failed to connect to database: {e}")
        finally:
            if conn:
                with contextlib.suppress(Exception):
                    conn.close()

    # --- tests ---

    def test_db_connection(self, db_connection):
        """Connection is established (fixture would fail otherwise)."""
        assert db_connection is not None  # minimal explicit assertion

    def test_db_version(self, db_connection):
        """Version query returns a non-empty PostgreSQL string."""
        with db_connection.cursor() as cur:
            cur.execute("SELECT version();")
            row = cur.fetchone()

        assert row is not None
        assert isinstance(row[0], str)
        assert "PostgreSQL" in row[0]
