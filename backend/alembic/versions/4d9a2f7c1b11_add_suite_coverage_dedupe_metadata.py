"""add suite coverage dedupe metadata

Revision ID: 4d9a2f7c1b11
Revises: cee93ba65d37
Create Date: 2026-03-28 23:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4d9a2f7c1b11"
down_revision = "cee93ba65d37"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _column_exists("prompt_suites", "generation_metadata"):
        op.add_column("prompt_suites", sa.Column("generation_metadata", sa.JSON(), nullable=True))
    if not _column_exists("prompt_suites", "coverage_report"):
        op.add_column("prompt_suites", sa.Column("coverage_report", sa.JSON(), nullable=True))
    if not _column_exists("prompt_suites", "dedupe_report"):
        op.add_column("prompt_suites", sa.Column("dedupe_report", sa.JSON(), nullable=True))

    if not _column_exists("prompt_suite_items", "coverage_topic_ids"):
        op.add_column("prompt_suite_items", sa.Column("coverage_topic_ids", sa.JSON(), nullable=True))
    if not _column_exists("prompt_suite_items", "coverage_topic_labels"):
        op.add_column("prompt_suite_items", sa.Column("coverage_topic_labels", sa.JSON(), nullable=True))
    if not _column_exists("prompt_suite_items", "generation_slot_index"):
        op.add_column("prompt_suite_items", sa.Column("generation_slot_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("prompt_suite_items", "generation_slot_index")
    op.drop_column("prompt_suite_items", "coverage_topic_labels")
    op.drop_column("prompt_suite_items", "coverage_topic_ids")
    op.drop_column("prompt_suites", "dedupe_report")
    op.drop_column("prompt_suites", "coverage_report")
    op.drop_column("prompt_suites", "generation_metadata")
