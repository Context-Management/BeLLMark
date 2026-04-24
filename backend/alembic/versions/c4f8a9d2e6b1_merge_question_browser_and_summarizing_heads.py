"""merge question browser and summarizing heads

Revision ID: c4f8a9d2e6b1
Revises: b1d2c3e4f5a6, e9b2d54d0c31
Create Date: 2026-04-12 14:05:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "c4f8a9d2e6b1"
down_revision: Union[str, Sequence[str], None] = ("b1d2c3e4f5a6", "e9b2d54d0c31")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge the independent schema heads without additional DDL."""


def downgrade() -> None:
    """Split the merged Alembic head without additional DDL."""
