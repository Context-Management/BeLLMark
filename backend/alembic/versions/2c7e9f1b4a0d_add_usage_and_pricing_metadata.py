"""add usage and pricing metadata

Revision ID: 2c7e9f1b4a0d
Revises: 15a40d42352b
Create Date: 2026-03-26 20:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c7e9f1b4a0d'
down_revision: Union[str, Sequence[str], None] = '15a40d42352b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('model_presets', sa.Column('price_source', sa.String(length=50), nullable=True))
    op.add_column('model_presets', sa.Column('price_source_url', sa.String(length=500), nullable=True))
    op.add_column('model_presets', sa.Column('price_checked_at', sa.DateTime(), nullable=True))
    op.add_column('model_presets', sa.Column('price_currency', sa.String(length=10), nullable=True))

    op.add_column('generations', sa.Column('input_tokens', sa.Integer(), nullable=True))
    op.add_column('generations', sa.Column('output_tokens', sa.Integer(), nullable=True))
    op.add_column('generations', sa.Column('cached_input_tokens', sa.Integer(), nullable=True))
    op.add_column('generations', sa.Column('reasoning_tokens', sa.Integer(), nullable=True))

    op.add_column('judgments', sa.Column('input_tokens', sa.Integer(), nullable=True))
    op.add_column('judgments', sa.Column('output_tokens', sa.Integer(), nullable=True))
    op.add_column('judgments', sa.Column('cached_input_tokens', sa.Integer(), nullable=True))
    op.add_column('judgments', sa.Column('reasoning_tokens', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('judgments', 'reasoning_tokens')
    op.drop_column('judgments', 'cached_input_tokens')
    op.drop_column('judgments', 'output_tokens')
    op.drop_column('judgments', 'input_tokens')

    op.drop_column('generations', 'reasoning_tokens')
    op.drop_column('generations', 'cached_input_tokens')
    op.drop_column('generations', 'output_tokens')
    op.drop_column('generations', 'input_tokens')

    op.drop_column('model_presets', 'price_currency')
    op.drop_column('model_presets', 'price_checked_at')
    op.drop_column('model_presets', 'price_source_url')
    op.drop_column('model_presets', 'price_source')
