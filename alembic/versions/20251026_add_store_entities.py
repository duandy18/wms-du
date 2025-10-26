"""no-op: superseded by 20251026_add_pdd_multi_store_shell"""

# 这条现在只是收束拓扑，不做任何 DDL
revision = "20251026_add_store_entities"
down_revision = "20251026_add_pdd_multi_store_shell"  # ★ 指向 12:30 那条
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
