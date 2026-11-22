"""Switch embedding column from 2048-dim (OpenRouter) to 384-dim (local all-MiniLM-L6-v2)

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-11-22

Drops the existing 2048-dim OpenRouter embeddings (they are incompatible with
the local all-MiniLM-L6-v2 384-dim model) and recreates the column typed as
vector(384).  All rows are set to NULL so the indexing worker will regenerate
embeddings on the next re-index using the local provider.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL out all stored embeddings first (avoids cast failure)
    op.execute("UPDATE code_chunks SET embedding = NULL")

    # Drop the old column (which may be vector(2048) or the wrong type)
    op.drop_column("code_chunks", "embedding")

    # Re-create as vector(384) for all-MiniLM-L6-v2
    op.add_column(
        "code_chunks",
        sa.Column("embedding", Vector(384), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("code_chunks", "embedding")
    op.add_column(
        "code_chunks",
        sa.Column("embedding", Vector(2048), nullable=True),
    )
