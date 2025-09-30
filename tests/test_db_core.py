import os
import contextlib
import psycopg2
import pytest
from dotenv import load_dotenv


# --- Test Setup ---
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
            # Yield the connection to the tests.
            yield conn
        except psycopg2.OperationalError as e:
            # If connection fails, fail the test immediately with a clear message.
            pytest.fail(f"Failed to connect to the database: {e}")
        finally:
            # Ensure the connection is closed, but only if it was successfully opened.
            if conn:
                # Use suppress to handle any potential errors during close, but
                # in this case, a simple close() is often enough.
                with contextlib.suppress(Exception):
                    conn.close()

    # --- Tests ---

    def test_db_connection(self, db_connection):
        """
        Tests if a database connection can be established successfully.
        """
        # The success of this test is implicitly verified by the fixture.
        # If the fixture completes without calling pytest.fail(), the connection is valid.
        print("\n✅ Successfully connected to the database.")

    def test_db_version(self, db_connection):
        """
        Executes a simple query to get the database version and verifies the result.
        """
        with db_connection.cursor() as cur:
            cur.execute("SELECT version();")
            row = cur.fetchone()

        # Assert that a row was returned and contains a string.
        assert row is not None
        assert isinstance(row[0], str)
        assert "PostgreSQL" in row[0]

        print(f"PostgreSQL version: {row[0]}")
