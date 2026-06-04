import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

class DatabaseClient:
    def __init__(self):
        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                1, 10,
                host=os.getenv("DB_HOST", "localhost"),
                port=os.getenv("DB_PORT", "5432"),
                database=os.getenv("DB_NAME", "shoe_store"),
                user=os.getenv("DB_USER", "postgres"),
                password=os.getenv("DB_PASSWORD", "")
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Error creating database connection pool: {e}")
            self.connection_pool = None

    def execute_query(self, query, params=None, fetch_all=True):
        """
        Thực thi câu lệnh SQL một cách an toàn với tham số truyền vào.
        """
        if not self.connection_pool:
            return {"error": "Database not connected"}

        conn = None
        try:
            # Debug log for SQL
            print(f"\n [DB] SQL: {query}")
            if params:
                print(f" [DB] PARAMS: {params}")

            conn = self.connection_pool.getconn()
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch_all:
                    columns = [desc[0] for desc in cursor.description]
                    results = cursor.fetchall()
                    return [dict(zip(columns, row)) for row in results]
                else:
                    conn.commit()
                    return {"status": "success"}
        except Exception as e:
            logger.error(f"Database query error: {e}")
            return {"error": str(e)}
        finally:
            if conn:
                self.connection_pool.putconn(conn)

# Singleton instance
db_client = DatabaseClient()
