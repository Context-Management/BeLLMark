"""merge_concurrency_and_spinoff_heads

Revision ID: 0fa12f302d9f
Revises: 3bd8a1ab866d, a1b2c3d4e5f6
Create Date: 2026-04-02 02:26:08.350367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fa12f302d9f'
down_revision: Union[str, Sequence[str], None] = ('3bd8a1ab866d', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
