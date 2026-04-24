"""add openrouter and ollama provider types

Revision ID: 80d312785804
Revises: a3f1c8d92b47
Create Date: 2026-03-01 17:09:04.027920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80d312785804'
down_revision: Union[str, Sequence[str], None] = 'a3f1c8d92b47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    SQLite stores ProviderType enum values as plain text strings, so adding
    new enum members (openrouter, ollama) requires no DDL changes. This
    migration exists solely to keep Alembic's version history in sync.
    """
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
