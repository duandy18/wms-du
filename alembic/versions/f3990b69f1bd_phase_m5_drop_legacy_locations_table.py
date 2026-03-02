"""phase m5: drop legacy locations table

Revision ID: f3990b69f1bd
Revises: ba5ce3f58da3
Create Date: 2026-03-02 11:51:31.334556

Location domain is deprecated.
- Drop all FKs referencing public.locations
- Then drop table public.locations

This migration is defensive across environments.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3990b69f1bd"
down_revision: Union[str, Sequence[str], None] = "ba5ce3f58da3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: drop legacy locations table."""

    conn = op.get_bind()
    insp = sa.inspect(conn)

    # If locations already gone, no-op.
    if not insp.has_table("locations", schema="public"):
        return

    # 1) Drop ALL FKs in public schema that reference public.locations
    conn.execute(
        sa.text(
            """
            DO $$
            DECLARE
              r record;
            BEGIN
              FOR r IN
                SELECT
                  con.conname AS conname,
                  rel.relname AS tablename
                FROM pg_constraint con
                JOIN pg_class rel ON rel.oid = con.conrelid
                JOIN pg_namespace n ON n.oid = rel.relnamespace
                WHERE n.nspname = 'public'
                  AND con.contype = 'f'
                  AND con.confrelid = 'public.locations'::regclass
              LOOP
                EXECUTE format('ALTER TABLE public.%I DROP CONSTRAINT %I', r.tablename, r.conname);
              END LOOP;
            END $$;
            """
        )
    )

    # 2) Drop the locations table (triggers are dropped automatically with table)
    op.drop_table("locations")


def downgrade() -> None:
    """Downgrade schema: best-effort minimal restore of locations table."""

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("current_item_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_item_id"],
            ["items.id"],
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_locations_wh_code"),
    )
