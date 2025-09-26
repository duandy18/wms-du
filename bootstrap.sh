#!/usr/bin/env bash
set -euo pipefail

# 项目环境一键初始化脚本
# 用法：./bootstrap.sh

echo ">>> 创建虚拟环境 .venv"
python3 -m venv .venv
source .venv/bin/activate

echo ">>> 升级 pip / 安装依赖"
pip install --upgrade pip
pip install -r requirements.txt

echo ">>> 安装 pre-commit 并启用钩子"
pip install pre-commit
pre-commit install

echo ">>> 初始化数据库 (SQLite 示例)"
mkdir -p db
sqlite3 db/app.db < db/schema.sql || true

echo ">>> 运行质量检查 (pre-commit + mypy + pytest)"
pre-commit run --all-files || true
mypy . || true
pytest --cov=app --cov-report=term-missing --cov-fail-under=80 || true

echo ">>> 开发环境初始化和测试完成！"
