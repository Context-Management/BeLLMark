"""add parent_run_id to benchmark_runs

Revision ID: a1b2c3d4e5f6
Revises: f74fa45582d1
Branch Labels: None
Depends On: None
Create Date: 2026-04-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f74fa45582d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(name: str) -> bool:
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name"),
        {"name": name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    """Add parent_run_id column to benchmark_runs — idempotent."""
    if not _column_exists("benchmark_runs", "parent_run_id"):
        # SQLite cannot add FK constraints via ALTER — add column without FK.
        # The FK is enforced at the ORM layer (models.py) and via PRAGMA foreign_keys=ON.
        op.add_column(
            "benchmark_runs",
            sa.Column(
                "parent_run_id",
                sa.Integer(),
                nullable=True,
            ),
        )
    if not _index_exists("ix_benchmark_runs_parent_run_id"):
        op.create_index(
            "ix_benchmark_runs_parent_run_id",
            "benchmark_runs",
            ["parent_run_id"],
            unique=False,
        )


def downgrade() -> None:
    """Remove parent_run_id column from benchmark_runs."""
    if _index_exists("ix_benchmark_runs_parent_run_id"):
        op.drop_index("ix_benchmark_runs_parent_run_id", table_name="benchmark_runs")
    # SQLite does not support DROP COLUMN in older versions; use batch_alter_table
    with op.batch_alter_table("benchmark_runs") as batch_op:
        batch_op.drop_column("parent_run_id")
