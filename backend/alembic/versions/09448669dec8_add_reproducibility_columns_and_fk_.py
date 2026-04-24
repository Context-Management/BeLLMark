"""add reproducibility columns and FK indexes

Revision ID: 09448669dec8
Revises: 648e990a9d68
Create Date: 2026-02-16 01:03:27.968957

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09448669dec8'
down_revision: Union[str, Sequence[str], None] = '648e990a9d68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


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
    if not _column_exists('benchmark_runs', 'random_seed'):
        op.add_column('benchmark_runs', sa.Column('random_seed', sa.Integer(), nullable=True))
    if not _column_exists('generations', 'model_version'):
        op.add_column('generations', sa.Column('model_version', sa.String(length=200), nullable=True))
    if not _column_exists('judgments', 'judge_temperature'):
        op.add_column('judgments', sa.Column('judge_temperature', sa.Float(), nullable=True))

    for idx_name, table, columns in [
        ('ix_generations_model_preset_id', 'generations', ['model_preset_id']),
        ('ix_generations_question_id', 'generations', ['question_id']),
        ('ix_judgments_generation_id', 'judgments', ['generation_id']),
        ('ix_judgments_judge_preset_id', 'judgments', ['judge_preset_id']),
        ('ix_judgments_question_id', 'judgments', ['question_id']),
        ('ix_prompt_suite_items_suite_id', 'prompt_suite_items', ['suite_id']),
        ('ix_question_attachments_attachment_id', 'question_attachments', ['attachment_id']),
        ('ix_question_attachments_question_id', 'question_attachments', ['question_id']),
        ('ix_questions_benchmark_id', 'questions', ['benchmark_id']),
        ('ix_suite_attachments_attachment_id', 'suite_attachments', ['attachment_id']),
        ('ix_suite_attachments_suite_id', 'suite_attachments', ['suite_id']),
    ]:
        if not _index_exists(idx_name):
            op.create_index(op.f(idx_name), table, columns, unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_suite_attachments_suite_id'), table_name='suite_attachments')
    op.drop_index(op.f('ix_suite_attachments_attachment_id'), table_name='suite_attachments')
    op.drop_index(op.f('ix_questions_benchmark_id'), table_name='questions')
    op.drop_index(op.f('ix_question_attachments_question_id'), table_name='question_attachments')
    op.drop_index(op.f('ix_question_attachments_attachment_id'), table_name='question_attachments')
    op.drop_index(op.f('ix_prompt_suite_items_suite_id'), table_name='prompt_suite_items')
    op.drop_index(op.f('ix_judgments_question_id'), table_name='judgments')
    op.drop_index(op.f('ix_judgments_judge_preset_id'), table_name='judgments')
    op.drop_index(op.f('ix_judgments_generation_id'), table_name='judgments')
    op.drop_column('judgments', 'judge_temperature')
    op.drop_index(op.f('ix_generations_question_id'), table_name='generations')
    op.drop_index(op.f('ix_generations_model_preset_id'), table_name='generations')
    op.drop_column('generations', 'model_version')
    op.drop_column('benchmark_runs', 'random_seed')
