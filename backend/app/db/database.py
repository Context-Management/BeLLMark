# backend/app/db/database.py
import os
from sqlalchemy import create_engine, event
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import sessionmaker, declarative_base

_DB_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DB_PATH = os.getenv("BELLMARK_DB_PATH") or os.path.join(_DB_DIR, "bellmark.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_DB_PATH}"

# Increase pool size to handle concurrent model generations
# With 17+ models running in parallel, we need at least 17 connections
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=30,
    pool_timeout=60  # Increase timeout to 60 seconds
)


# Enable WAL mode for better read/write concurrency
# WAL mode allows readers while a write is in progress
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout for locks
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
