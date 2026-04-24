# backend/tests/test_database.py
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base, set_sqlite_pragma


@pytest.fixture()
def db_session_with_pragmas():
    """Create an in-memory DB with the real pragma listener attached."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine, "connect", set_sqlite_pragma)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_foreign_keys_enabled(db_session_with_pragmas):
    """Verify SQLite foreign key enforcement is on."""
    result = db_session_with_pragmas.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1, "Foreign keys must be enabled"


def test_model_preset_and_generation_support_pricing_provenance_and_usage_fields():
    """Pricing provenance and usage columns should be part of the ORM metadata."""
    from app.db.models import Generation, Judgment, ModelPreset

    assert hasattr(ModelPreset, "price_source")
    assert hasattr(ModelPreset, "price_source_url")
    assert hasattr(ModelPreset, "price_checked_at")
    assert hasattr(ModelPreset, "price_currency")
    assert hasattr(Generation, "input_tokens")
    assert hasattr(Generation, "output_tokens")
    assert hasattr(Generation, "cached_input_tokens")
    assert hasattr(Generation, "reasoning_tokens")
    assert hasattr(Judgment, "input_tokens")
    assert hasattr(Judgment, "output_tokens")
    assert hasattr(Judgment, "cached_input_tokens")
    assert hasattr(Judgment, "reasoning_tokens")
