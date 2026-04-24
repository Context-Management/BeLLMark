"""add suite criteria and expected answer columns

Revision ID: 65d87b34e148
Revises: 33284c6a6797
Create Date: 2026-02-24 18:45:35.895077

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65d87b34e148'
down_revision: Union[str, Sequence[str], None] = '33284c6a6797'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def upgrade() -> None:
    """Upgrade schema — idempotent."""
    if not _column_exists('prompt_suites', 'default_criteria'):
        op.add_column('prompt_suites', sa.Column('default_criteria', sa.JSON(), nullable=True))

    if not _column_exists('prompt_suite_items', 'expected_answer'):
        op.add_column('prompt_suite_items', sa.Column('expected_answer', sa.Text(), nullable=True))

    if not _column_exists('questions', 'expected_answer'):
        op.add_column('questions', sa.Column('expected_answer', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('questions', 'expected_answer')
    op.drop_column('prompt_suite_items', 'expected_answer')
    op.drop_column('prompt_suites', 'default_criteria')
