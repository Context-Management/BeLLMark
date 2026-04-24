"""add generations model_preset_id question_id index

Revision ID: b1d2c3e4f5a6
Revises: 0fa12f302d9f
Create Date: 2026-04-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1d2c3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "0fa12f302d9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        op.f("ix_generations_model_preset_id_question_id"),
        "generations",
        ["model_preset_id", "question_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_generations_model_preset_id_question_id"), table_name="generations")
