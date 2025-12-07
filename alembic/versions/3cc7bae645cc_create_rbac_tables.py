# alembic/versions/3cc7bae645cc_create_rbac_tables.py

"""create rbac tables

Revision ID: 3cc7bae645cc
Revises: ef524e72a68a
Create Date: 2025-11-24 10:58:57.133235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3cc7bae645cc"
down_revision: Union[str, Sequence[str], None] = "ef524e72a68a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
  """Upgrade schema: create roles table (and future RBAC objects if需要)."""
  op.create_table(
      "roles",
      sa.Column("id", sa.Integer, primary_key=True),
      sa.Column("name", sa.String(length=255), nullable=False, unique=True),
      sa.Column("description", sa.Text(), nullable=True),
  )


def downgrade() -> None:
  """Downgrade schema."""
  op.drop_table("roles")
