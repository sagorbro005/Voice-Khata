import os
import sys

# Add backend directory to sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

import ledger_db

DB_PATH: str = os.path.join(os.path.dirname(__file__), "voice_khata.db")

def reset_database() -> None:
    """Reset SQLite database by dropping all tables and re-initializing current schema."""
    print(f"Resetting database schema at '{DB_PATH}'...")
    with ledger_db.get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS sale_items")
        cursor.execute("DROP TABLE IF EXISTS sales_transactions")
        cursor.execute("DROP TABLE IF EXISTS entries")
        conn.commit()
    
    ledger_db.init_db(DB_PATH)
    print("[OK] Voice Khata database successfully reset and re-initialized.")

if __name__ == "__main__":
    reset_database()
