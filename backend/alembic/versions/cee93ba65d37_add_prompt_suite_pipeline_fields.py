"""add prompt suite pipeline fields

Revision ID: cee93ba65d37
Revises: 2c7e9f1b4a0d
Create Date: 2026-03-27 11:30:57.172189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cee93ba65d37'
down_revision: Union[str, Sequence[str], None] = '2c7e9f1b4a0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add category, difficulty, and criteria columns to prompt_suite_items."""
    op.add_column('prompt_suite_items', sa.Column('category', sa.String(), nullable=True))
    op.add_column('prompt_suite_items', sa.Column('difficulty', sa.String(), nullable=True))
    op.add_column('prompt_suite_items', sa.Column('criteria', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Remove category, difficulty, and criteria columns from prompt_suite_items."""
    op.drop_column('prompt_suite_items', 'criteria')
    op.drop_column('prompt_suite_items', 'difficulty')
    op.drop_column('prompt_suite_items', 'category')
