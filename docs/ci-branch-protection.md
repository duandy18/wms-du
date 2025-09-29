# CI & Branch Protection — Confirmation Sheet  
# CI 与分支保护 — 确认表

> Status: **ENFORCED** on `main`  
> 状态：已对 `main` **强制生效**

---

## 1) What runs in CI / CI 包含哪些 Job

Workflow: **`app-ci`** (`.github/workflows/ci.yml`)

- **lint-type** — ruff、black、isort、mypy  
- **migrate-check** — `alembic upgrade head` on Postgres  
- **tests (sqlite)** — pytest on SQLite  
- **tests (mysql)** — pytest on MySQL 8  
- **coverage-gate** — 总覆盖率阈值 **≥ 70%**；PR 上运行 **diff-cover ≥ 85%**  
- **build** — Docker Build & Push to GHCR（仅 `push` 事件执行）  
- **all-checks** — 汇总门（aggregator），依赖上面所有必需 job  

---

## 2) Branch Protection (main) / 主分支保护（main）

**Required options / 必选项**

- [x] Require status checks to pass before merging  
  已绑定的检查（当前）：  
  - `app-ci / all-checks`  
  - `app-ci / build`  
  - `app-ci / tests (postgres)`  
  - `app-ci / tests (sqlite)`  
  - `app-ci / lint-type`

- [x] Require branches to be up to date before merging  
- [x] At least one approving review  
- [x] Disallow force pushes / prevent branch deletion  

---

## 3) Coverage Gates / 覆盖率闸门

- **Global coverage (总覆盖率)**:  
  `pytest --cov=app --cov-fail-under=70`  
  → **≥ 70%** required to pass.

- **Diff coverage (差异覆盖率)**:  
  `diff-cover coverage.xml --compare-branch=origin/main --fail-under=85`  
  → **≥ 85%** required for new / changed code.

---

## 4) Merge Strategy / 合并策略

- 日常开发 → `dev`  
- PR → base = `dev`  
- 定期稳定合并 → `dev → main`  
- `main` only accepts PR with all checks green.  

> Never push directly to `main`.  
> **禁止直接 push main。**

---

## 5) Future Notes / 后续说明

- 如果 CI job 名称有调整，确保更新 **Branch Protection**。  
- 如果覆盖率阈值上调（如 75% / 80%），同步更新：  
  - `pyproject.toml` → `[tool.coverage.report].fail_under`  
  - CI workflow `coverage-gate` job
