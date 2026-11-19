"""add pgvector embedding column

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-10-22 13:00:00.000000

Converts the placeholder JSON ``embedding`` column on ``code_chunks`` into a
pgvector ``vector(384)`` column so Module 6 can store and query dense
embeddings produced by the all-MiniLM-L6-v2 model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# all-MiniLM-L6-v2 produces 384-dimensional embeddings.
EMBEDDING_DIMENSION: int = 384


def upgrade() -> None:
    """Upgrade schema."""
    # Enable the pgvector extension. Idempotent. Requires the ``vector``
    # extension to be installed on the PostgreSQL server (the project's
    # existing PostgreSQL + pgvector setup).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Convert the placeholder JSON column into a typed vector column. Prior to
    # this module the column was always NULL (embeddings were not populated),
    # so casting with ``USING NULL`` discards nothing.
    op.alter_column(
        "code_chunks",
        "embedding",
        existing_type=sa.JSON(),
        type_=Vector(EMBEDDING_DIMENSION),
        existing_nullable=True,
        postgresql_using="NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "code_chunks",
        "embedding",
        existing_type=Vector(EMBEDDING_DIMENSION),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="NULL",
    )
    # The vector extension is intentionally left installed: it is shared
    # infrastructure and may be referenced by other objects.
