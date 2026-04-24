"""initial schema

Revision ID: 648e990a9d68
Revises:
Create Date: 2026-02-16 00:43:53.530185

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect as sa_inspect
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '648e990a9d68'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """Check if a table already exists (idempotent migration guard)."""
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
    """Upgrade schema — fully idempotent, safe to run on existing databases."""
    if not _table_exists('attachments'):
        op.create_table('attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=500), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_attachments_id'):
        op.create_index(op.f('ix_attachments_id'), 'attachments', ['id'], unique=False)

    if not _table_exists('model_presets'):
        op.create_table('model_presets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('provider', sa.Enum('lmstudio', 'openai', 'anthropic', 'google', 'mistral', 'deepseek', 'grok', 'glm', 'kimi', name='providertype'), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('model_id', sa.String(length=200), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('price_input', sa.Float(), nullable=True),
        sa.Column('price_output', sa.Float(), nullable=True),
        sa.Column('supports_vision', sa.Integer(), nullable=True),
        sa.Column('context_limit', sa.Integer(), nullable=True),
        sa.Column('is_reasoning', sa.Integer(), nullable=True),
        sa.Column('reasoning_level', sa.Enum('none', 'low', 'medium', 'high', 'xhigh', 'max', name='reasoninglevel'), nullable=True),
        sa.Column('custom_temperature', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_model_presets_id'):
        op.create_index(op.f('ix_model_presets_id'), 'model_presets', ['id'], unique=False)

    if not _table_exists('prompt_suites'):
        op.create_table('prompt_suites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_prompt_suites_id'):
        op.create_index(op.f('ix_prompt_suites_id'), 'prompt_suites', ['id'], unique=False)
    if not _index_exists('ix_prompt_suites_name'):
        op.create_index(op.f('ix_prompt_suites_name'), 'prompt_suites', ['name'], unique=False)

    if not _table_exists('benchmark_runs'):
        op.create_table('benchmark_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', 'cancelled', name='runstatus'), nullable=True),
        sa.Column('judge_mode', sa.Enum('separate', 'comparison', name='judgemode'), nullable=False),
        sa.Column('criteria', sa.JSON(), nullable=False),
        sa.Column('model_ids', sa.JSON(), nullable=False),
        sa.Column('judge_ids', sa.JSON(), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('temperature_mode', sa.Enum('normalized', 'provider_default', 'custom', name='temperaturemode'), nullable=True),
        sa.Column('run_config_snapshot', sa.JSON(), nullable=True),
        sa.Column('source_suite_id', sa.Integer(), nullable=True),
        sa.Column('total_context_tokens', sa.Integer(), nullable=True),
        sa.Column('comment_summaries', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['source_suite_id'], ['prompt_suites.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_benchmark_runs_id'):
        op.create_index(op.f('ix_benchmark_runs_id'), 'benchmark_runs', ['id'], unique=False)

    if not _table_exists('prompt_suite_items'):
        op.create_table('prompt_suite_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('suite_id', sa.Integer(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=True),
        sa.Column('system_prompt', sa.String(), nullable=True),
        sa.Column('user_prompt', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['suite_id'], ['prompt_suites.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_prompt_suite_items_id'):
        op.create_index(op.f('ix_prompt_suite_items_id'), 'prompt_suite_items', ['id'], unique=False)

    if not _table_exists('suite_attachments'):
        op.create_table('suite_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('suite_id', sa.Integer(), nullable=False),
        sa.Column('attachment_id', sa.Integer(), nullable=False),
        sa.Column('scope', sa.Enum('all_questions', 'specific', name='suiteattachmentscope'), nullable=True),
        sa.Column('suite_item_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['attachment_id'], ['attachments.id'], ),
        sa.ForeignKeyConstraint(['suite_id'], ['prompt_suites.id'], ),
        sa.ForeignKeyConstraint(['suite_item_id'], ['prompt_suite_items.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_suite_attachments_id'):
        op.create_index(op.f('ix_suite_attachments_id'), 'suite_attachments', ['id'], unique=False)

    if not _table_exists('questions'):
        op.create_table('questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('benchmark_id', sa.Integer(), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('user_prompt', sa.Text(), nullable=False),
        sa.Column('context_tokens', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['benchmark_id'], ['benchmark_runs.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_questions_id'):
        op.create_index(op.f('ix_questions_id'), 'questions', ['id'], unique=False)

    if not _table_exists('generations'):
        op.create_table('generations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('model_preset_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tokens', sa.Integer(), nullable=True),
        sa.Column('raw_chars', sa.Integer(), nullable=True),
        sa.Column('answer_chars', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'success', 'failed', name='taskstatus'), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retries', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['model_preset_id'], ['model_presets.id'], ),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_generations_id'):
        op.create_index(op.f('ix_generations_id'), 'generations', ['id'], unique=False)

    if not _table_exists('question_attachments'):
        op.create_table('question_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('attachment_id', sa.Integer(), nullable=False),
        sa.Column('inherited', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['attachment_id'], ['attachments.id'], ),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_question_attachments_id'):
        op.create_index(op.f('ix_question_attachments_id'), 'question_attachments', ['id'], unique=False)

    if not _table_exists('judgments'):
        op.create_table('judgments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('judge_preset_id', sa.Integer(), nullable=False),
        sa.Column('generation_id', sa.Integer(), nullable=True),
        sa.Column('blind_mapping', sa.JSON(), nullable=True),
        sa.Column('rankings', sa.JSON(), nullable=True),
        sa.Column('scores', sa.JSON(), nullable=True),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('comments', sa.JSON(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('tokens', sa.Integer(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'running', 'success', 'failed', name='taskstatus'), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('retries', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['generation_id'], ['generations.id'], ),
        sa.ForeignKeyConstraint(['judge_preset_id'], ['model_presets.id'], ),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if not _index_exists('ix_judgments_id'):
        op.create_index(op.f('ix_judgments_id'), 'judgments', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_judgments_id'), table_name='judgments')
    op.drop_table('judgments')
    op.drop_index(op.f('ix_question_attachments_id'), table_name='question_attachments')
    op.drop_table('question_attachments')
    op.drop_index(op.f('ix_generations_id'), table_name='generations')
    op.drop_table('generations')
    op.drop_index(op.f('ix_questions_id'), table_name='questions')
    op.drop_table('questions')
    op.drop_index(op.f('ix_suite_attachments_id'), table_name='suite_attachments')
    op.drop_table('suite_attachments')
    op.drop_index(op.f('ix_prompt_suite_items_id'), table_name='prompt_suite_items')
    op.drop_table('prompt_suite_items')
    op.drop_index(op.f('ix_benchmark_runs_id'), table_name='benchmark_runs')
    op.drop_table('benchmark_runs')
    op.drop_index(op.f('ix_prompt_suites_name'), table_name='prompt_suites')
    op.drop_index(op.f('ix_prompt_suites_id'), table_name='prompt_suites')
    op.drop_table('prompt_suites')
    op.drop_index(op.f('ix_model_presets_id'), table_name='model_presets')
    op.drop_table('model_presets')
    op.drop_index(op.f('ix_attachments_id'), table_name='attachments')
    op.drop_table('attachments')
