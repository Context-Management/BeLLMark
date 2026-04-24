"""add is_archived to model_presets

Revision ID: e4e77f9a615e
Revises: 80d312785804
Create Date: 2026-03-04 13:12:31.633352

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4e77f9a615e'
down_revision: Union[str, Sequence[str], None] = '80d312785804'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_archived column for soft-delete of model presets."""
    op.add_column('model_presets', sa.Column('is_archived', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Remove is_archived column."""
    op.drop_column('model_presets', 'is_archived')
