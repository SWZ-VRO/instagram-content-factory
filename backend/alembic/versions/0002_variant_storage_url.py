"""add variants.storage_url

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11

Supports the "supabase" storage backend (backend/services/storage.py) --
needed for hosts with no persistent disk (e.g. Render's free tier). Nullable
and unused when STORAGE_BACKEND=local (the Docker Compose default).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("variants", sa.Column("storage_url", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("variants", "storage_url")
