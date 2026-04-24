"""add_concurrency_settings

Revision ID: 3bd8a1ab866d
Revises: c8f19d4e2a41
Create Date: 2026-04-02 01:54:00.840080

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bd8a1ab866d'
down_revision: Union[str, Sequence[str], None] = 'c8f19d4e2a41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'concurrency_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('server_key', sa.String(500), nullable=True),
        sa.Column('max_concurrency', sa.Integer(), nullable=False),
        sa.UniqueConstraint('provider', 'server_key', name='uq_concurrency_provider_server'),
    )
    op.add_column('benchmark_runs', sa.Column('sequential_mode', sa.Boolean(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('benchmark_runs', 'sequential_mode')
    op.drop_table('concurrency_settings')
