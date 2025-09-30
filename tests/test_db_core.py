import os
import contextlib

import psycopg2
import pytest
from dotenv import load_dotenv


# 跳过 SQLite CI 上的整个模块 (如果环境变量 DATABASE_URL 指向 SQLite)
@pytest.mark.skipif(
    os.getenv("DATABASE_URL", "").startswith("sqlite"),
    reason="Skip DB tests on SQLite CI"
)
class TestDatabaseCore:
    """
    针对 PostgreSQL 数据库核心功能的测试。
    所有测试将使用一个连接, 并在类测试完成后关闭。
    """

    # 确保 psycopg2 可用
    pytest.importorskip("psycopg2")

    @pytest.fixture(scope="class")
    def db_config(self):
        """从环境变量中加载数据库配置。"""
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
        提供数据库连接, 在类测试完成后关闭。
        """
        conn = None
        try:
            # 建立连接
            conn = psycopg2.connect(
                dbname=db_config["dbname"],
                user=db_config["user"],
                password=db_config["password"],
                host=db_config["host"],
                port=db_config["port"],
            )
            yield conn
        except psycopg2.OperationalError as e:
            # 如果连接失败, 测试立即失败
            pytest.fail(f"Failed to connect to database: {e}")
        finally:
            # 确保连接被关闭
            if conn:
                # 使用 suppress 来处理关闭时可能出现的任何异常
                with contextlib.suppress(Exception):
                    conn.close()

    def test_db_version(self, db_connection):
        """
        测试执行一个简单的查询(获取数据库版本), 确保连接正常工作。
        """
        # 使用游标作为上下文管理器以确保其被正确关闭
        with db_connection.cursor() as cur:
            cur.execute("SELECT version();")
            row = cur.fetchone()

        assert row is not None
        assert isinstance(row[0], str)
        assert "PostgreSQL" in row[0]

    def test_database_crud_operations(self, db_connection):
        """
        测试数据库的创建、读取和删除操作(CRUD),
        以验证权限和事务是否正常工作。
        """
        table_name = "test_data_for_ci"

        # 确保游标和事务在测试后清理
        with db_connection.cursor() as cur:

            # --- 1. 创建表 (CREATE) ---
            cur.execute(f"DROP TABLE IF EXISTS {table_name};")
            cur.execute(f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # --- 2. 插入数据 (CREATE/WRITE) ---
            insert_value = "ci_test_data"
            cur.execute(
                f"INSERT INTO {table_name} (value) VALUES (%s) RETURNING id;",
                (insert_value,)
            )  # 将长行拆分成两行
            inserted_id = cur.fetchone()[0]

            # --- 3. 查询数据 (READ) ---
            cur.execute(f"SELECT value FROM {table_name} WHERE id = %s;", (inserted_id,))
            read_value = cur.fetchone()

            # 断言读取的值与插入的值匹配
            assert read_value is not None
            assert read_value[0] == insert_value

            # --- 4. 删除数据 (DELETE) ---
            cur.execute(f"DELETE FROM {table_name} WHERE id = %s;", (inserted_id,))
            cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE id = %s;", (inserted_id,))
            count = cur.fetchone()[0]

            # 断言数据已被删除
            assert count == 0

            # --- 5. 清理 (Cleanup) ---
            cur.execute(f"DROP TABLE {table_name};")

            # 提交所有更改, 确保它们写入数据库
            db_connection.commit()
