#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------
# WMS-DU bootstrap script
# 本地开发环境一键初始化
# ----------------------------------------

# 1. 创建虚拟环境
if [ ! -d ".venv" ]; then
  echo "📦 创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi

# 2. 激活虚拟环境
echo "✅ 激活虚拟环境"
# shellcheck disable=SC1091
source .venv/bin/activate

# 3. 升级 pip 基础工具
echo "⬆️ 升级 pip/setuptools/wheel ..."
python -m pip install -U pip setuptools wheel

# 4. 安装依赖
if [ -f "requirements.txt" ]; then
  echo "📥 安装 requirements.txt 依赖..."
  pip install -r requirements.txt
else
  echo "⚠️ 未找到 requirements.txt，安装最小依赖集合（兜底）"
  pip install fastapi "uvicorn[standard]" sqlalchemy "pydantic[email]" \
              pytest pytest-cov pre-commit ruff black isort mypy httpx pydantic-settings
fi

# 5. 安装 pre-commit 钩子（如有）
if [ -f ".pre-commit-config.yaml" ]; then
  echo "🔧 安装 pre-commit 钩子..."
  pre-commit install
fi

# 6. 运行质量检查（第一次可能会自动修复，非零退出不阻塞）
echo "🧪 运行质量检查：pre-commit / mypy / pytest(>=80%)"
pre-commit run --all-files || true
mypy . || true
pytest --cov=app --cov-report=term-missing --cov-fail-under=80 || true

echo "🎉 环境初始化完成！后续进入项目只需："
echo "   cd ~/wms-du && source .venv/bin/activate"
