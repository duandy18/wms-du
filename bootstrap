#!/usr/bin/env bash
set -euo pipefail

# ----------------------------------------
# WMS-DU bootstrap script
# 用于本地开发环境初始化
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

# 3. 升级 pip
echo "⬆️ 升级 pip..."
pip install --upgrade pip setuptools wheel

# 4. 安装依赖
if [ -f "requirements.txt" ]; then
  echo "📥 安装 requirements.txt 依赖..."
  pip install -r requirements.txt
else
  echo "⚠️ 未找到 requirements.txt，跳过依赖安装"
fi

# 5. 初始化 pre-commit
if [ -f ".pre-commit-config.yaml" ]; then
  echo "🔧 安装 pre-commit 钩子..."
  pre-commit install
fi

echo "🎉 环境初始化完成，可以开始开发啦！"
