# ruff: noqa: RUF001, RUF003
# scripts/seed_rbac.py
# ruff: noqa: RUF003

"""
Seed RBAC roles & permissions into the database.

- Creates roles: admin, buyer, ops, auditor
- Creates permissions: purchase:create, purchase:view, purchase:approve,
  inbound:receive, inventory:view
- Binds roles <-> permissions
- Optionally grants the earliest user (min id) the admin role, using raw SQL
  to avoid ORM/column mismatch with existing users table.

幂等:重复运行不会产生重复行.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text, select
from sqlalchemy.orm import Session

# 确保项目根在 sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal
from app.models import Role, Permission, role_permissions, user_roles  # noqa


ROLE_PERMS = {
    "admin": [
        "purchase:create",
        "purchase:view",
        "purchase:approve",
        "inbound:receive",
        "inventory:view",
    ],
    "buyer": ["purchase:create", "purchase:view"],
    "ops": ["inbound:receive", "purchase:view"],
    "auditor": ["inventory:view", "purchase:view"],
}


def get_or_create(model, session: Session, defaults=None, **kwargs):
    inst = session.query(model).filter_by(**kwargs).one_or_none()
    if inst:
        return inst, False
    params = dict(kwargs)
    params.update(defaults or {})
    inst = model(**params)
    session.add(inst)
    return inst, True


def grant_admin_to_first_user(db: Session) -> None:
    """
    尝试把最早的一个用户(最小 id)授予 admin 角色.
    用原生 SQL 仅查询 id,避免 ORM 因列不匹配而报错.
    """
    try:
        # 1) 拿到最小的用户 id(仅查 id,不触发 ORM 列选择)
        row = db.execute(text("SELECT id FROM users ORDER BY id ASC LIMIT 1")).first()
        if not row:
            print("ℹ️  未找到任何用户,跳过授予 admin.")
            return
        user_id = row[0]

        # 2) 查 admin 角色 id(用 ORM 查 Role 只涉及 roles 表,不会受 users 影响)
        admin_role = db.query(Role).filter_by(name="admin").one_or_none()
        if not admin_role:
            print("⚠️  未找到 admin 角色,跳过授予.")
            return
        role_id = admin_role.id

        # 3) 判断是否已存在绑定
        exists = db.execute(
            text(
                "SELECT 1 FROM user_roles WHERE user_id = :u AND role_id = :r LIMIT 1"
            ),
            {"u": user_id, "r": role_id},
        ).first()

        if exists:
            print(f"ℹ️  用户 {user_id} 已经是 admin,跳过.")
            return

        # 4) 插入绑定
        db.execute(
            text("INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r)"),
            {"u": user_id, "r": role_id},
        )
        print(f"✅ 已将用户 {user_id} 授予 admin.")
    except Exception as e:
        # 柔性失败:不阻断整个 seed 过程
        print(f"⚠️  授予 admin 时发生错误,已跳过:{e}")


def main():
    db: Session = SessionLocal()
    try:
        # 1) 确保所有权限存在
        codes = {c for codes in ROLE_PERMS.values() for c in codes}
        perm_objs = {}
        for code in sorted(codes):
            p, _ = get_or_create(Permission, db, code=code)
            perm_objs[code] = p

        # 2) 角色存在并绑定权限(幂等)
        for role_name, codes in ROLE_PERMS.items():
            r, _ = get_or_create(Role, db, name=role_name)
            r.permissions = [perm_objs[c] for c in sorted(set(codes))]
            db.add(r)

        # 3) 可选:把最早用户授予 admin(用原生 SQL,只查 id)
        grant_admin_to_first_user(db)

        db.commit()
        print("✅ Seed RBAC done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
