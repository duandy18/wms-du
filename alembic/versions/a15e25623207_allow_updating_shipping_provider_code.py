"""allow updating shipping_provider code

Revision ID: a15e25623207
Revises: 6c86cf2f97a7
Create Date: 2026-03-26 16:28:03.507231

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a15e25623207"
down_revision: Union[str, Sequence[str], None] = "6c86cf2f97a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_shipping_providers_code_immutable ON shipping_providers;")
    op.execute("DROP FUNCTION IF EXISTS trg_forbid_update_shipping_providers_code();")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.trg_forbid_update_shipping_providers_code()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
          IF NEW.code IS DISTINCT FROM OLD.code THEN
            RAISE EXCEPTION 'shipping_providers.code is immutable';
          END IF;
          RETURN NEW;
        END;
        $function$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_shipping_providers_code_immutable
        BEFORE UPDATE ON public.shipping_providers
        FOR EACH ROW
        EXECUTE FUNCTION trg_forbid_update_shipping_providers_code();
        """
    )
