"""
Database Migration Script for AnyLegal AI

This script handles database schema migrations, allowing for safe updates
to the database structure without altering the main database.py file directly.
"""
import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'anylegal_oss.db'))

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    logger.info(f"Migrations connecting to database: {DATABASE_PATH}")
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def table_exists(cursor, table_name):
    """Checks if a table exists in the database."""
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    return cursor.fetchone() is not None

def column_exists(cursor, table_name, column_name):
    """Checks if a column exists in a given table."""

    if not table_exists(cursor, table_name):
        return False

    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row['name'] for row in cursor.fetchall()]
    return column_name in columns

def run_migrations():
    """
    Applies all necessary database migrations.
    This function is idempotent and can be run safely on every startup.
    """
    logger.info("Running database migrations...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if table_exists(cursor, 'threads'):
            if not column_exists(cursor, 'threads', 'jurisdiction'):
                logger.info("Applying migration: Adding 'jurisdiction' column to 'threads' table.")
                cursor.execute("ALTER TABLE threads ADD COLUMN jurisdiction TEXT")
                logger.info("Migration successful for 'threads' table.")
            else:
                logger.debug("'jurisdiction' column already exists in 'threads' table. Skipping.")
        else:
            logger.info("'threads' table does not exist yet. Skipping jurisdiction column migration.")

        if table_exists(cursor, 'chat_history'):
            if not column_exists(cursor, 'chat_history', 'jurisdiction'):
                logger.info("Applying migration: Adding 'jurisdiction' column to 'chat_history' table.")
                cursor.execute("ALTER TABLE chat_history ADD COLUMN jurisdiction TEXT")
                logger.info("Migration successful for 'chat_history' table.")
            else:
                logger.debug("'jurisdiction' column already exists in 'chat_history' table. Skipping.")
        else:
            logger.info("'chat_history' table does not exist yet. Skipping jurisdiction column migration.")

        if table_exists(cursor, 'threads'):
            if not column_exists(cursor, 'threads', 'thread_type'):
                logger.info("Applying migration: Adding 'thread_type' column to 'threads' table.")
                cursor.execute("ALTER TABLE threads ADD COLUMN thread_type TEXT DEFAULT 'research'")
                logger.info("Migration successful: 'thread_type' column added.")
            else:
                logger.debug("'thread_type' column already exists in 'threads' table. Skipping.")

        if table_exists(cursor, 'threads'):
            if not column_exists(cursor, 'threads', 'document_id'):
                logger.info("Applying migration: Adding 'document_id' column to 'threads' table.")
                cursor.execute("ALTER TABLE threads ADD COLUMN document_id TEXT")
                logger.info("Migration successful: 'document_id' column added.")

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_threads_document_id ON threads(document_id)")
                logger.info("Index created on document_id.")
            else:
                logger.debug("'document_id' column already exists in 'threads' table. Skipping.")

        if table_exists(cursor, 'threads'):
            if not column_exists(cursor, 'threads', 'document_name'):
                logger.info("Applying migration: Adding 'document_name' column to 'threads' table.")
                cursor.execute("ALTER TABLE threads ADD COLUMN document_name TEXT")
                logger.info("Migration successful: 'document_name' column added.")
            else:
                logger.debug("'document_name' column already exists in 'threads' table. Skipping.")

        conn.commit()
        conn.close()
        logger.info("Database migrations completed successfully.")

    except sqlite3.Error as e:
        logger.error(f"Database migration failed: {e}", exc_info=True)

        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during database migration: {e}", exc_info=True)
        raise

if __name__ == '__main__':

    print("Running manual database migration...")
    logging.basicConfig(level=logging.INFO)
    run_migrations()
    print("Manual migration finished.") 