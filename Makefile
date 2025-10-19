# Makefile — WMS-DU stable workflow shortcuts
# ===========================================
# 目标：一行命令完成格式化、检测、测试与提交
#
# 双轨模式：
# - make dev-commit        # 开发提交（跳过钩子），追求快速迭代
# - make release-commit    # 发布提交（全量检查），保证主干稳定

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

PYTHON          ?= python
PIP             ?= $(PYTHON) -m pip
RUFF            ?= ruff
BLACK           ?= black
ISORT           ?= isort
PRECOMMIT       ?= pre-commit
DETECT_SECRETS  ?= detect-secrets
RUN_SH          ?= bash run.sh

REPO_ROOT       := $(shell git rev-parse --show-toplevel 2>/dev/null)

.DEFAULT_GOAL := help

# ---------- 帮助 ----------
.PHONY: help
help:
	@echo ""
	@echo "Usage:"
	@echo "  make fix            - isort + black + ruff --fix（不阻塞）"
	@echo "  make fmt            - 仅 isort + black"
	@echo "  make lint           - Ruff 全量检查（严格）"
	@echo "  make punct          - 测试代码中文全角标点 -> 半角（tests/）"
	@echo "  make quick          - 运行快速用例（bash run.sh quick）"
	@echo "  make smoke          - 运行冒烟用例（bash run.sh smoke）"
	@echo "  make hooks          - 安装/更新 pre-commit 钩子，并清缓存"
	@echo "  make hooks-run      - 本地对所有文件执行 pre-commit（只观察）"
	@echo "  make secrets-scan   - 本地对照 .secrets.baseline 扫描"
	@echo "  make mypy           - 类型检查（不阻塞，供点检）"
	@echo "  make ci             - 本地模拟 CI：fix + lint + quick"
	@echo "  make dev-commit     - 开发提交（跳过钩子），快速推进"
	@echo "  make release-commit - 发布提交（fix+lint+quick 全通过后提交）"
	@echo "  make clean-cache    - 清理 ruff/pytest/mypy 缓存"
	@echo ""

# ---------- 格式化 ----------
.PHONY: fmt
fmt:
	@echo "== isort . =="
	$(ISORT) .
	@echo "== black . =="
	$(BLACK) .

.PHONY: fix
fix:
	@echo "== normalize fullwidth punctuation in tests =="
	$(PYTHON) tools/normalize_punct.py tests || true
	@echo "== isort . =="
	$(ISORT) .
	@echo "== black . =="
	$(BLACK) .
	@echo "== ruff --fix（不阻塞）=="
	# Ruff 自动修复能修的；有剩余问题也不在 fix 阶段失败
	$(RUFF) check --fix app tests scripts tools || true

# ---------- Lint ----------
.PHONY: lint
lint:
	@echo "== Ruff 全面检查（严格） =="
	$(RUFF) check app tests scripts tools

# ---------- 测试 ----------
.PHONY: quick
quick:
	@echo "== run.sh quick =="
	$(RUN_SH) quick

.PHONY: smoke
smoke:
	@echo "== run.sh smoke =="
	$(RUN_SH) smoke

# ---------- 半角化（只处理 tests/，避免误伤业务字符串） ----------
.PHONY: punct
punct:
	@echo "== normalize fullwidth punctuation in tests =="
	$(PYTHON) tools/normalize_punct.py tests

# ---------- pre-commit ----------
.PHONY: hooks
hooks:
	@echo "== 安装 pre-commit 钩子 =="
	$(PRECOMMIT) install
	$(PRECOMMIT) install -t pre-push || true
	@echo "== 清理隔离环境缓存 =="
	$(PRECOMMIT) clean

.PHONY: hooks-run
hooks-run:
	@echo "== pre-commit run --all-files（仅观察） =="
	$(PRECOMMIT) run --all-files || true

# ---------- detect-secrets ----------
.PHONY: secrets-scan
secrets-scan:
	@echo "== detect-secrets scan --baseline .secrets.baseline --all-files =="
	cd "$(REPO_ROOT)"; \
	$(DETECT_SECRETS) scan --baseline .secrets.baseline --all-files

# ---------- mypy ----------
.PHONY: mypy
mypy:
	@echo "== mypy（仅 app/；不阻塞） =="
	$(PYTHON) -m mypy app || true

# ---------- CI 本地模拟 ----------
.PHONY: ci
ci:
	@echo "== CI: 格式化（fix） =="
	$(MAKE) fix
	@echo "== CI: Lint（ruff） =="
	$(MAKE) lint
	@echo "== CI: Quick 测试 =="
	$(MAKE) quick
	@echo "== CI: Done ✅ =="

# ---------- 提交工作流 ----------
.PHONY: dev-commit
dev-commit:
	@echo "== 开发提交（跳过钩子） =="
	git add -A
	git commit -m "wip(dev): auto save" --no-verify
	git push

.PHONY: release-commit
release-commit:
	@echo "== 发布提交：fix + lint + quick =="
	$(MAKE) fix
	$(MAKE) lint
	$(MAKE) quick
	@echo "== 全通过，执行提交 =="
	git add -A
	git commit -m "chore(release): style & checks passed"
	git push

# ---------- 清理缓存 ----------
.PHONY: clean-cache
clean-cache:
	@echo "== 清理缓存目录 =="
	rm -rf .pytest_cache .ruff_cache .mypy_cache 2>/dev/null || true
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
