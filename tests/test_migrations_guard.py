# tests/test_migrations_guard.py
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from typing import Iterable, Optional

# ---------- 基础路径 ----------
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _find_alembic_ini(search_from: pathlib.Path) -> Optional[pathlib.Path]:
    """
    在仓库内查找最近的 alembic.ini。
    优先级：仓库根 -> 一级子目录 -> 递归。
    """
    # 1) 根目录直查
    ini = search_from / "alembic.ini"
    if ini.exists():
        return ini

    # 2) 常见子目录尝试（apps/, app/, backend/）
    candidates = [
        search_from / "apps" / "alembic.ini",
        search_from / "app" / "alembic.ini",
        search_from / "backend" / "alembic.ini",
    ]
    for c in candidates:
        if c.exists():
            return c

    # 3) 递归查找（深度有限，避免太慢）
    for p in search_from.rglob("alembic.ini"):
        # 忽略 venv/node_modules 等
        s = str(p)
        if any(seg in s for seg in ("/.venv/", "/venv/", "/node_modules/", "/.git/")):
            continue
        return p
    return None


def _alembic(cmd: list[str], *, env: dict | None = None, cwd: pathlib.Path | None = None) -> str:
    """
    运行 alembic 子命令，返回 stdout。非零退出抛异常，带完整输出。
    """
    r = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return r.stdout


def _upgrade_head(ini: pathlib.Path, db_url: str) -> str:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    return _alembic(["alembic", "-c", str(ini), "upgrade", "head"], env=env, cwd=ini.parent)


def _autogen_once(ini: pathlib.Path, message: str, db_url: str) -> list[pathlib.Path]:
    """
    运行一次 autogenerate。若产生迁移文件，返回文件列表（并负责删除以保持工作树干净）。
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    out_before = set((ini.parent / "versions").glob("*.py")) if (ini.parent / "versions").exists() else set()
    try:
        _alembic(["alembic", "-c", str(ini), "revision", "--autogenerate", "-m", message], env=env, cwd=ini.parent)
    except subprocess.CalledProcessError as e:
        # 有些工程会在无变化时抛带有 "No changes in schema detected" 的非零退出；兼容这类实现
        if "No changes in schema detected" in (e.stdout or ""):
            return []
        raise
    out_after = set((ini.parent / "versions").glob("*.py")) if (ini.parent / "versions").exists() else set()
    created = sorted(out_after - out_before)
    # 清理刚生成的迁移文件，保持仓库整洁
    for f in created:
        with contextlib.suppress(Exception):
            f.unlink()
    return created


def _sqlite_url(tmpdir: pathlib.Path) -> str:
    return f"sqlite:///{tmpdir/'alembic_guard.db'}"


# ----------------------------- 测试主体 -----------------------------
import contextlib
import pytest


def test_alembic_upgrade_and_autogenerate_guard(tmp_path: pathlib.Path) -> None:
    """
    1) 升级到 head 成功；
    2) autogenerate 不应产生迁移文件（否则说明 ORM 与迁移脚本存在差异）。
    """
    ini = _find_alembic_ini(ROOT)
    assert ini and ini.exists(), (
        "未找到 alembic.ini。请确认你的迁移配置存在，或将本测试调整为 pytest.skip。"
        "查找范围: 仓库根及其子目录。"
    )

    db_url = _sqlite_url(tmp_path)

    # 升级应成功
    out = _upgrade_head(ini, db_url)
    # 一个温和的 sanity check：日志需包含 upgrade 关键字
    assert "upgrade" in out.lower()

    # autogenerate 一次，若有文件生成 -> 失败
    created = _autogen_once(ini, "TMP_GUARD_CHECK", db_url)
    assert not created, f"检测到待生成迁移: {', '.join(str(p.name) for p in created)}（ORM 与迁移不一致）"
