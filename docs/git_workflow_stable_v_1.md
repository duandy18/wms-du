# 🧭 WMS-DU Git 与格式化稳定规范 v1
> 目标：让开发时间花在代码上，而不是与 pre-commit、Git、格式化打架。

---

## 一、全局原则
- **统一行宽**：88（Black / Ruff / isort 一致）。
- **唯一格式化源**：Black 为主，Ruff 辅助，isort 负责 import 顺序。
- **严禁**在 commit 阶段自动改文件后又阻断提交（必要时跳过钩子）。
- **detect-secrets 与 mypy 仅在 CI 或手动执行**，不阻断日常 commit。
- **alembic/**、`_alembic_bak/`、`docs/canvas/`、`*.bak`、前端目录等一律排除。

---

## 二、日常开发 6 步法

1. **起分支**
   ```bash
   git switch main && git pull --ff-only
   git switch -c feat/phase2.6-xxx
   ```

2. **写代码**
   VSCode 保存时自动格式化；尽量一次改完一个功能。

3. **格式修复**
   ```bash
   make fix   # 等价于 isort . && black . && ruff check --fix .
   ```

4. **本地测试**
   ```bash
   bash run.sh quick
   ```

5. **提交**
   ```bash
   git add -A
   git commit -m "feat: xxx"
   # 若钩子报错且只改格式：
   git commit --no-verify -m "style: auto-format"
   ```

6. **推送并开 PR**
   ```bash
   git push -u origin feat/phase2.6-xxx
   ```

---

## 三、遇到钩子阻断时

| 钩子 | 处理方式 |
|------|-----------|
| **detect-secrets** | 不在本地跑。让 CI 检测。若必要：<br> `detect-secrets scan --baseline .secrets.baseline --all-files` |
| **mypy** | 长期任务，逐模块治理。业务提交不阻断。 |
| **ruff/black/isort** | 再执行 `git add -A` 重新提交；仍不行则 `--no-verify`。 |

---

## 四、统一 Git 配置（一次设置）

```bash
git config --global push.autoSetupRemote true
git config --global pull.rebase true
git config --global rerere.enabled true
git config --global core.autocrlf input
git config --global core.safecrlf warn
```

---

## 五、编辑器推荐配置（VSCode）

`.vscode/settings.json`：

```json
{
  "editor.formatOnSave": true,
  "python.formatting.provider": "black",
  "ruff.lint.args": ["--fix"],
  "ruff.lint.run": "onSave",
  "python.analysis.autoImportCompletions": true
}
```

---

## 六、Makefile 常用命令

```makefile
.PHONY: fmt lint fix quick smoke

fmt:
	isort .
	black .

lint:
	ruff check app tests

fix:
	isort .
	black .
	ruff check --fix .

quick:
	bash run.sh quick

smoke:
	bash run.sh smoke
```

---

## 七、CI 最小健康线

| Job | 内容 | 是否阻断 |
|------|------|-----------|
| **Style** | ruff / black / isort | ✅ |
| **Quick** | bash run.sh quick | ✅ |
| **Detect-secrets** | 使用 .secrets.baseline | ⏸（初期可选） |
| **Mypy** | 限 app/ 范围 | ⏸（逐步启用） |

---

## 八、分支与 PR 命名约定

| 类型 | 前缀 | 示例 |
|------|-------|------|
| 新功能 | `feat/` | feat/phase2.6-events |
| 修 Bug | `fix/` | fix/putaway-rollback |
| 样式清理 | `chore/style-` | chore/style-and-secrets-cleanup |
| 类型补充 | `chore/mypy-` | chore/mypy-snapshot |
| CI 调整 | `chore/ci-` | chore/ci-tune-main |
| 脚本维护 | `tools/` | tools/db-checker |

---

## 九、忽略与豁免清单
- Ruff / mypy 不扫描：
  ```
  alembic/**
  _alembic_bak/**
  docs/canvas/**
  *.bak
  *.md
  frontend/**
  ```
- detect-secrets 排除：
  ```
  --exclude-files "(alembic/versions\.bak/|docs/canvas/|.*\.md$|.*\.bak$)"
  ```

---

## 十、一次性清理分支操作（大规模格式化）

```bash
git switch main && git pull
git switch -c chore/style-and-secrets-cleanup
make fix
detect-secrets scan --baseline .secrets.baseline --all-files
git add -A
git commit --no-verify -m "chore(style): global format & secret baseline sync"
git push -u origin chore/style-and-secrets-cleanup
```

合并后即可长期稳定，主线 CI 保证风格与安全基线不再波动。

---

## 十一、推荐 PR 检查项
- ✅ CI “App CI – Lite” 全绿
- ✅ 无新增 secrets 报警
- ✅ 无 import 未用 / 未排序
- ✅ 本地 `run.sh quick` 通过
- 🛌 mypy 报错仅出现在待治理模块（非阻断）

---

## 十二、总结
> - 一次配置，全体遵循。
> - “开发 = 写代码 + 一键修 + 一键测”。
> - 遇钩子改文件：再 `git add` 一次，不要慌。
> - detect-secrets 与 mypy 慢慢修，不要阻塞日常。
> - 所有清理动作都在 `chore/` 下集中完成。
