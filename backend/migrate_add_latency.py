#!/usr/bin/env python3
"""
Migration: Add latency_ms columns to generations and judgments tables.

This script adds the latency_ms column to track response latency
in milliseconds for both generations and judgments.
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
    # Check generations table
    cursor.execute("PRAGMA table_info(generations)")
    gen_columns = [row[1] for row in cursor.fetchall()]

    if "latency_ms" not in gen_columns:
        print("Adding latency_ms column to generations table...")
        cursor.execute(
            "ALTER TABLE generations ADD COLUMN latency_ms INTEGER"
        )
        print("Added latency_ms to generations table.")
    else:
        print("latency_ms column already exists in generations table.")

    # Check judgments table
    cursor.execute("PRAGMA table_info(judgments)")
    jud_columns = [row[1] for row in cursor.fetchall()]

    if "latency_ms" not in jud_columns:
        print("Adding latency_ms column to judgments table...")
        cursor.execute(
            "ALTER TABLE judgments ADD COLUMN latency_ms INTEGER"
        )
        print("Added latency_ms to judgments table.")
    else:
        print("latency_ms column already exists in judgments table.")

    conn.commit()
    print("Migration completed successfully!")

except sqlite3.Error as e:
    print(f"Migration failed: {e}")
    conn.rollback()
    exit(1)
finally:
    conn.close()
