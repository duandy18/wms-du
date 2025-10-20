# alembic/versions/u1_outbound_commits_unique.py
from alembic import op
import sqlalchemy as sa

revision = "u1_outbound_commits_unique"
down_revision = "e1e0g01"  # 按你的链条调整
branch_labels = None
depends_on = None


def _get_cols(bind, table):
    insp = sa.inspect(bind)
    return {c["name"].lower() for c in insp.get_columns(table)}


def upgrade():
    bind = op.get_bind()
    cols = _get_cols(bind, "outbound_commits")

    # 猜测 / 适配各仓库可能的命名
    platform_candidates = ["platform", "provider", "source"]
    ref_candidates      = ["ref", "order_ref", "order_id", "external_ref"]
    state_candidates    = ["state", "status", "state_code"]

    def pick(cands):
        for c in cands:
            if c in cols:
                return c
        return None

    p_col = pick(platform_candidates)
    r_col = pick(ref_candidates)
    s_col = pick(state_candidates)

    # 若缺失标准列，补上（可空），并尽量从候选列回填一次
    if p_col is None:
        op.add_column("outbound_commits", sa.Column("platform", sa.String(32), nullable=True))
        if "provider" in cols:
            op.execute("UPDATE outbound_commits SET platform = provider WHERE platform IS NULL")
        elif "source" in cols:
            op.execute("UPDATE outbound_commits SET platform = source WHERE platform IS NULL")
        p_col = "platform"

    if r_col is None:
        op.add_column("outbound_commits", sa.Column("ref", sa.String(64), nullable=True))
        for alt in ["order_ref", "order_id", "external_ref"]:
            if alt in cols:
                op.execute(f"UPDATE outbound_commits SET ref = {alt} WHERE ref IS NULL")
                break
        r_col = "ref"

    if s_col is None:
        op.add_column("outbound_commits", sa.Column("state", sa.String(32), nullable=True))
        for alt in ["status", "state_code"]:
            if alt in cols:
                op.execute(f"UPDATE outbound_commits SET state = {alt} WHERE state IS NULL")
                break
        s_col = "state"

    # 统一创建唯一索引（用索引而不是约束，适配度更高）
    # 注意：这里直接用列名，不做表达式 COALESCE；允许 NULL 的场景下，PG 的唯一索引对多个 NULL 不冲突，符合“只对实际值幂等”的预期
    op.create_index(
        "ux_outbound_commits_3cols",
        "outbound_commits",
        [p_col, r_col, s_col],
        unique=True,
    )


def downgrade():
    bind = op.get_bind()
    cols = _get_cols(bind, "outbound_commits")

    # 尝试移除索引（不管当时绑定的是哪个三列名，索引名固定）
    try:
        op.drop_index("ux_outbound_commits_3cols", table_name="outbound_commits")
    except Exception:
        pass

    # 保守回退：不删除可能补充的列，避免数据丢失；如需彻底回退，可按需手动 drop column
