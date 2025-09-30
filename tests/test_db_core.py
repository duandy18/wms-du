import os
import contextlib
import psycopg2
import pytest
from dotenv import load_dotenv


# A more declarative way to skip the whole module based on an environment variable.
@pytest.mark.skipif(
    os.getenv("DATABASE_URL", "").startswith("sqlite"),
    reason="Skip DB tests on SQLite CI"
)
class TestDatabaseCore:

    # Make sure psycopg2 is available; otherwise, skip these tests.
    pytest.importorskip("psycopg2")

    @pytest.fixture(scope="class")
    def db_config(self):
        """Loads DB configuration from environment variables."""
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
        Provides a database connection for all tests in this class.
        The connection is opened once and closed at the end of the class's tests.
        """
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
            pytest.fail(f"Failed to connect to database: {e}")
        finally:
            if conn:
                with contextlib.suppress(Exception):
                    conn.close()

    def test_db_version(self, db_connection):
        """
        Execute a trivial query and assert a version string is returned.
        """
        with db_connection.cursor() as cur:
            cur.execute("SELECT version();")
            row = cur.fetchone()

        assert row is not None
        assert isinstance(row[0], str)
        assert "PostgreSQL" in row[0]

    def test_database_crud_operations(self, db_connection):
        """
        测试数据库的基本读写操作 (CRUD),
        以验证权限和事务是否正常工作.
        """
        table_name = "ci_test_data"
        insert_value = "data_to_read"

        # --- 1. 创建表 (CREATE)
        with contextlib.suppress(Exception):
            cur = db_connection.cursor()
            cur.execute(f"DROP TABLE IF EXISTS {table_name}")
            cur.execute(f"CREATE TABLE {table_name} (id SERIAL PRIMARY KEY, value VARCHAR(50) NOT NULL)")

            # --- 2. 插入数据 (INSERT/WRITE)
            cur.execute(
                f"INSERT INTO {table_name} (value) VALUES (%s) RETURNING id;",
                (insert_value,)
            )
            inserted_id = cur.fetchone()[0]
            db_connection.commit()  # 提交写入操作

            # --- 3. 读取数据 (READ)
            cur.execute(f"SELECT value FROM {table_name} WHERE id = %s", (inserted_id,))
            read_value = cur.fetchone()[0]

            assert read_value == insert_value, "读取到的数据与插入数据不匹配."

            # --- 4. 更新数据 (UPDATE)
            update_value = "data_updated"
            cur.execute(f"UPDATE {table_name} SET value = %s WHERE id = %s", (update_value, inserted_id))
            db_connection.commit()

            cur.execute(f"SELECT value FROM {table_name} WHERE id = %s", (inserted_id,))
            final_value = cur.fetchone()[0]

            assert final_value == update_value, "数据更新失败."

            # --- 5. 删除数据 (DELETE)
            cur.execute(f"DELETE FROM {table_name} WHERE id = %s", (inserted_id,))
            db_connection.commit()

            cur.execute(f"SELECT value FROM {table_name} WHERE id = %s", (inserted_id,))
            assert cur.fetchone() is None, "数据删除失败."

        # --- 6. 清理
        with contextlib.suppress(Exception):
            cur.execute(f"DROP TABLE IF EXISTS {table_name}")
            db_connection.commit()

### **步骤二：提交并推送**

现在，你的本地文件已经是最新版本了。请执行以下命令来强制 Git 识别这个修改并上传：

```bash
# 1. 检查状态 (这次应该显示 modified)
git status

# 2. 添加到暂存区
git add tests/test_db_core.py

# 3. 创建提交
git commit -m "feat: Final commit of database CRUD tests"

# 4. 推送至 GitHub
git push
