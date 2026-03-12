"""enforce_surcharge_config_invariants

Revision ID: 04aa7e1aa68b
Revises: b230ce6e75cc
Create Date: 2026-03-10 17:02:30.517218
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "04aa7e1aa68b"
down_revision: Union[str, Sequence[str], None] = "b230ce6e75cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # config invariant
    # ---------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_validate_sp_surcharge_config_on_config()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_city_n integer;
        BEGIN

            IF NEW.province_mode = 'cities' THEN
                IF NEW.fixed_amount <> 0 THEN
                    RAISE EXCEPTION
                        'shipping_provider_surcharge_configs: fixed_amount must be 0 when province_mode=cities';
                END IF;
            END IF;

            IF NEW.province_mode = 'province' THEN
                SELECT COUNT(*)
                INTO v_city_n
                FROM shipping_provider_surcharge_config_cities
                WHERE config_id = NEW.id;

                IF v_city_n > 0 THEN
                    RAISE EXCEPTION
                        'shipping_provider_surcharge_configs: province mode cannot keep city rows';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sp_surcharge_config_on_config
        AFTER INSERT OR UPDATE
        ON shipping_provider_surcharge_configs
        FOR EACH ROW
        EXECUTE FUNCTION trg_validate_sp_surcharge_config_on_config();
        """
    )

    # ---------------------------------------------------------
    # city invariant
    # ---------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_validate_sp_surcharge_config_on_city()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_mode varchar(16);
        BEGIN

            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;

            SELECT province_mode
            INTO v_mode
            FROM shipping_provider_surcharge_configs
            WHERE id = NEW.config_id;

            IF v_mode IS NULL THEN
                RAISE EXCEPTION
                    'shipping_provider_surcharge_config_cities: parent config not found';
            END IF;

            IF v_mode <> 'cities' THEN
                RAISE EXCEPTION
                    'shipping_provider_surcharge_config_cities: city rows require parent province_mode=cities';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_sp_surcharge_config_on_city
        AFTER INSERT OR UPDATE
        ON shipping_provider_surcharge_config_cities
        FOR EACH ROW
        EXECUTE FUNCTION trg_validate_sp_surcharge_config_on_city();
        """
    )


def downgrade() -> None:

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_sp_surcharge_config_on_city
        ON shipping_provider_surcharge_config_cities;
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS trg_validate_sp_surcharge_config_on_city();
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_sp_surcharge_config_on_config
        ON shipping_provider_surcharge_configs;
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS trg_validate_sp_surcharge_config_on_config();
        """
    )
