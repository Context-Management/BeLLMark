"""add generation started_at column

Revision ID: a3f1c8d92b47
Revises: 65d87b34e148
Create Date: 2026-03-01

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c8d92b47'
down_revision: Union[str, Sequence[str], None] = '65d87b34e148'
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
    if not _column_exists('generations', 'started_at'):
        op.add_column('generations', sa.Column('started_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('generations', 'started_at')
