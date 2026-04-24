"""add elo_ratings and elo_history tables

Revision ID: f74fa45582d1
Revises: 09448669dec8
Create Date: 2026-02-16 02:10:22.563630

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f74fa45582d1'
down_revision: Union[str, Sequence[str], None] = '09448669dec8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """Check if a table already exists."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return name in inspector.get_table_names()


def _index_exists(name: str) -> bool:
    """Check if an index already exists."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name"),
        {"name": name}
    )
    return result.fetchone() is not None


def upgrade() -> None:
    """Upgrade schema — idempotent."""
    if not _table_exists('elo_ratings'):
        op.create_table('elo_ratings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_preset_id', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('uncertainty', sa.Float(), nullable=True),
        sa.Column('games_played', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['model_preset_id'], ['model_presets.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_elo_ratings_id'):
        op.create_index(op.f('ix_elo_ratings_id'), 'elo_ratings', ['id'], unique=False)
    if not _index_exists('ix_elo_ratings_model_preset_id'):
        op.create_index(op.f('ix_elo_ratings_model_preset_id'), 'elo_ratings', ['model_preset_id'], unique=True)

    if not _table_exists('elo_history'):
        op.create_table('elo_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('model_preset_id', sa.Integer(), nullable=False),
        sa.Column('benchmark_run_id', sa.Integer(), nullable=False),
        sa.Column('rating_before', sa.Float(), nullable=False),
        sa.Column('rating_after', sa.Float(), nullable=False),
        sa.Column('games_in_run', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['benchmark_run_id'], ['benchmark_runs.id'], ),
        sa.ForeignKeyConstraint(['model_preset_id'], ['model_presets.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_elo_history_benchmark_run_id'):
        op.create_index(op.f('ix_elo_history_benchmark_run_id'), 'elo_history', ['benchmark_run_id'], unique=False)
    if not _index_exists('ix_elo_history_id'):
        op.create_index(op.f('ix_elo_history_id'), 'elo_history', ['id'], unique=False)
    if not _index_exists('ix_elo_history_model_preset_id'):
        op.create_index(op.f('ix_elo_history_model_preset_id'), 'elo_history', ['model_preset_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_elo_history_model_preset_id'), table_name='elo_history')
    op.drop_index(op.f('ix_elo_history_id'), table_name='elo_history')
    op.drop_index(op.f('ix_elo_history_benchmark_run_id'), table_name='elo_history')
    op.drop_table('elo_history')
    op.drop_index(op.f('ix_elo_ratings_model_preset_id'), table_name='elo_ratings')
    op.drop_index(op.f('ix_elo_ratings_id'), table_name='elo_ratings')
    op.drop_table('elo_ratings')
