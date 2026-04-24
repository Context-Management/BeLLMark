"""add lmstudio metadata fields

Revision ID: 9016f1288ab4
Revises: 4d9a2f7c1b11
Create Date: 2026-03-29 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9016f1288ab4"
down_revision = "4d9a2f7c1b11"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _column_exists("model_presets", "parameter_count"):
        op.add_column("model_presets", sa.Column("parameter_count", sa.String(length=50), nullable=True))
    if not _column_exists("model_presets", "quantization_bits"):
        op.add_column("model_presets", sa.Column("quantization_bits", sa.Float(), nullable=True))
    if not _column_exists("model_presets", "selected_variant"):
        op.add_column("model_presets", sa.Column("selected_variant", sa.String(length=255), nullable=True))
    if not _column_exists("model_presets", "model_architecture"):
        op.add_column("model_presets", sa.Column("model_architecture", sa.String(length=100), nullable=True))
    if not _column_exists("model_presets", "reasoning_detection_source"):
        op.add_column("model_presets", sa.Column("reasoning_detection_source", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("model_presets", "reasoning_detection_source")
    op.drop_column("model_presets", "model_architecture")
    op.drop_column("model_presets", "selected_variant")
    op.drop_column("model_presets", "quantization_bits")
    op.drop_column("model_presets", "parameter_count")
