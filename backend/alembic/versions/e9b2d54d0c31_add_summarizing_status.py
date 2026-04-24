"""add summarizing status

Revision ID: e9b2d54d0c31
Revises: 0fa12f302d9f
Create Date: 2026-04-02 17:43:37.619572

SQLite stores enum values as plain TEXT, so no DDL is needed to add
the new 'summarizing' value to RunStatus. This migration is a no-op
that advances the Alembic head pointer as a paper trail.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9b2d54d0c31'
down_revision: Union[str, Sequence[str], None] = '0fa12f302d9f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: SQLite stores enum values as plain strings; adding 'summarizing'
    to the Python RunStatus enum is sufficient."""
    pass


def downgrade() -> None:
    """No-op: SQLite TEXT column accepts any string value."""
    pass
