"""add score rationales to judgments

Revision ID: d5c6e7f8a9b0
Revises: c4f8a9d2e6b1
Create Date: 2026-04-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d5c6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "c4f8a9d2e6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("judgments", sa.Column("score_rationales", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("judgments", "score_rationales")
