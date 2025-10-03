#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Bootstrapping WMS-DU development environment..."

# 1) 创建虚拟环境（如果不存在）
if [ ! -d ".venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv .venv
fi

# 2) 激活虚拟环境
echo "📂 Activating virtual environment..."
# shellcheck disable=SC1091
source .venv/bin/activate

# 3) 升级 pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# 4) 安装运行时依赖
if [ -f "requirements.txt" ]; then
  echo "📥 Installing runtime dependencies..."
  pip install -r requirements.txt
fi

# 5) 安装开发依赖
if [ -f "requirements-dev.txt" ]; then
  echo "🛠 Installing dev dependencies..."
  pip install -r requirements-dev.txt
else
  echo "⚠️ No requirements-dev.txt found, skipping dev tools."
fi

# 6) 安装 pre-commit 钩子
if command -v pre-commit &>/dev/null; then
  echo "🔗 Installing pre-commit hooks..."
  pre-commit install
else
  echo "⚠️ pre-commit not available, please install manually."
fi

# 7) 提示完成
echo "✅ Bootstrap finished! You can now run:"
echo "   pre-commit run --all-files"
echo "   mypy ."
echo "   pytest --cov=app --cov-report=term-missing --cov-fail-under=80"
