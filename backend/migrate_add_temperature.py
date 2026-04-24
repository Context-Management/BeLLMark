#!/usr/bin/env python3
"""
Migration: Add temperature column to benchmark_runs table.

This script adds the temperature column with a default value of 0.8
to the benchmark_runs table in the SQLite database.
"""

import sqlite3
from pathlib import Path

# Database path
db_path = Path(__file__).parent / "bellmark.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    print("Skipping migration - database will be created with the new schema.")
    exit(0)

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if temperature column already exists
    cursor.execute("PRAGMA table_info(benchmark_runs)")
    columns = [row[1] for row in cursor.fetchall()]

    if "temperature" in columns:
        print("Temperature column already exists. Migration not needed.")
    else:
        print("Adding temperature column to benchmark_runs table...")
        cursor.execute(
            "ALTER TABLE benchmark_runs ADD COLUMN temperature REAL DEFAULT 0.8"
        )
        conn.commit()
        print("Migration completed successfully!")

except sqlite3.Error as e:
    print(f"Migration failed: {e}")
    conn.rollback()
    exit(1)
finally:
    conn.close()
