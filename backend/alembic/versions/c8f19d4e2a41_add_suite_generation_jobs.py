"""add suite generation jobs

Revision ID: c8f19d4e2a41
Revises: 9016f1288ab4
Create Date: 2026-03-30 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f19d4e2a41'
down_revision: Union[str, Sequence[str], None] = '9016f1288ab4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'suite_generation_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', name='runstatus'), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('topic', sa.Text(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('generator_model_ids', sa.JSON(), nullable=False),
        sa.Column('editor_model_id', sa.Integer(), nullable=False),
        sa.Column('reviewer_model_ids', sa.JSON(), nullable=False),
        sa.Column('pipeline_config', sa.JSON(), nullable=False),
        sa.Column('coverage_mode', sa.String(length=50), nullable=False),
        sa.Column('coverage_spec', sa.JSON(), nullable=True),
        sa.Column('max_topics_per_question', sa.Integer(), nullable=False),
        sa.Column('context_attachment_id', sa.Integer(), nullable=True),
        sa.Column('phase', sa.String(length=50), nullable=True),
        sa.Column('snapshot_payload', sa.JSON(), nullable=True),
        sa.Column('checkpoint_payload', sa.JSON(), nullable=True),
        sa.Column('suite_id', sa.Integer(), nullable=True),
        sa.Column('partial_suite_id', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['context_attachment_id'], ['attachments.id']),
        sa.ForeignKeyConstraint(['editor_model_id'], ['model_presets.id']),
        sa.ForeignKeyConstraint(['partial_suite_id'], ['prompt_suites.id']),
        sa.ForeignKeyConstraint(['suite_id'], ['prompt_suites.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id'),
    )
    op.create_index(op.f('ix_suite_generation_jobs_id'), 'suite_generation_jobs', ['id'], unique=False)
    op.create_index(op.f('ix_suite_generation_jobs_session_id'), 'suite_generation_jobs', ['session_id'], unique=True)
    op.create_index(op.f('ix_suite_generation_jobs_status'), 'suite_generation_jobs', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_suite_generation_jobs_status'), table_name='suite_generation_jobs')
    op.drop_index(op.f('ix_suite_generation_jobs_session_id'), table_name='suite_generation_jobs')
    op.drop_index(op.f('ix_suite_generation_jobs_id'), table_name='suite_generation_jobs')
    op.drop_table('suite_generation_jobs')
