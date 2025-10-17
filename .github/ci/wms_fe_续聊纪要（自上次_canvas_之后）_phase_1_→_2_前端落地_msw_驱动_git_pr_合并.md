# WMS‑FE 续聊纪要（自上次 Canvas 之后）

> 范围：承接“上一个 Canvas 之后”的所有对话与产出，聚焦 **前端 Phase 1→2 接力、MSW 驱动联调、VS Code/编辑器稳态设置、脚本式补丁落地、Git 分支/PR 合并流程**。

---

## 0. 目标与现状
- 目标：**首页库存快照 + 三大任务页（Inbound/Putaway/Outbound）+ 工具（Stock/Ledger）** 在 **MSW 驱动**下先飞，随后切真后端。
- 现状：
  - 首页 Snapshot 可切 **图块/表格**；支持**分布抽屉（库位/批次）**。
  - 三大任务页入口 + 工具页最小可用；**Outbound** 带 ref 幂等与可用量提示。
  - **MSW 已成功接管**（[MSW] Mocking enabled / started），`/snapshot/inventory` 命中 200。
  - 通过 PR 已将前端初始化合入 `main`（Squash merge）。

---

## 1. 一次性补丁与文件结构（Phase 1→2）
- **patch_phase1_to_2.sh**：新增/改动：
  - `src/pages/SnapshotPage.tsx`、`components/snapshot/*`、`components/common/ApiBadge.tsx`
  - `pages/InboundPage/PutawayPage/OutboundPage`、`pages/tools/StockToolPage/LedgerToolPage`
  - `mocks/handlers/snapshot.ts / outbound.ts / index.ts`、`mocks/browser.ts`
  - `lib/api.ts`（统一 GET/POST）与 `lib/csv.ts`、`types/inventory.ts`
  - `router.tsx`（导航与路由）
- 运行顺序：
  1) `pnpm i` 安装依赖
  2) `bash tools/patch_phase1_to_2.sh`
  3) `pnpm dev`
- 自检脚本：`tools/selfcheck_phase1_to_2.sh`

---

## 2. Phase 2 壳子（Tasks/Batches/Moves）
- **patch_phase2_shells.sh**：新增：
  - `pages/TasksPage.tsx`、`pages/BatchesPage.tsx`、`pages/MovesPage.tsx`
  - `mocks/handlers/tasks.ts / batches.ts / moves.ts` 并在 `handlers/index.ts` 导出
  - 路由注入 `/tasks /batches /moves`
- 自检脚本：`tools/selfcheck_phase2_shells.sh`

---

## 3. MSW 启动与“Unexpected token '<'”排障闭环
**症状**：首屏空白/Failed to fetch/Unexpected token '<'（拿到 `index.html` 不是 JSON）。

**关键修复点：**
1) **main.tsx 异步非阻塞启动 MSW**，并在 `window.__MSW_ENABLED__` 标记 + `MSW_READY` 事件：
```ts
if (import.meta.env.DEV && import.meta.env.VITE_USE_MSW === '1') {
  (window as any).__MSW_ENABLED__ = 'starting'
  import('./mocks/browser')
    .then(async ({ worker }) => {
      await worker.start({ serviceWorker: { url: '/mockServiceWorker.js' }, onUnhandledRequest: 'bypass' })
      ;(window as any).__MSW_ENABLED__ = true
      window.dispatchEvent(new Event('MSW_READY'))
    })
    .catch(() => { (window as any).__MSW_ENABLED__ = false })
}
```
2) **ApiBadge** 监听 `MSW_READY` + 轮询，避免首屏误判。
3) **api.ts：MSW 优先 + 自动补斜杠**：
```ts
function _base(){
  const api=(import.meta.env.VITE_API_URL||'').replace(/\/$/,'')
  return ((window as any).__MSW_ENABLED__===true || !api) ? '' : api
}
const joinPath=(p:string)=>p.startsWith('/')?p:'/'+p
export async function apiGet<T>(path:string){ const res=await fetch(_base()+joinPath(path)); if(!res.ok) throw new Error(`[GET ${path}] ${res.status}`); return res.json() }
export async function apiPost<T>(path:string, body:any){ const res=await fetch(_base()+joinPath(path), {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)}); if(!res.ok) throw new Error(`[POST ${path}] ${res.status}`); return res.json() }
```
4) **handlers 用“域通配”**：`http.get('*/snapshot/inventory', ...)`，保证任意 host 命中。
5) 生成 `public/mockServiceWorker.js`：`npx msw init public --save`。
6) **强刷两次**（Ctrl+Shift+R）/ 清理 SW：
```js
navigator.serviceWorker.getRegistrations().then(rs=>rs.forEach(r=>r.unregister()))
```
7) **SnapshotPage** 加 `MSW_READY` 自动重试与“刷新”按钮，避免首屏竞态。

**验证要点**：
- Console：`[MSW] Mocking enabled`、`[MSW] started`
- Network：`/snapshot/inventory` 200（ServiceWorker 响应）
- Console 直接 `fetch('/snapshot/inventory').then(r=>r.json())` 打印 tiles 数组

---

## 4. VS Code / 编辑器稳态配置
- `.vscode/settings.json`：关闭 shell/yaml 自动格式化；TS/TSX/JSON on-save 格式化；粘贴为纯文本快捷键（`Ctrl+Alt+V`）。
- `.editorconfig`：统一换行与缩进，`.sh` 禁止自动修饰。
- 备选编辑器：**micro**（禁自动缩进/换行）、**Neovim**、**Sublime**、**Gedit/Kate**。

---

## 5. 扩容 mock 数据（多商品）
- `tiles` 扩展出 12 个 SKU（猫粮/冻干/罐头/膏类），带规格、Top2 库位、主批次与临期标记。
- 可选支持查询与分页：`/snapshot/inventory?q=&offset=&limit=`（前端后续接入搜索/分页器）。

---

## 6. Git 流程（本次实操复盘）
**问题**：本地 `git init` 的前端首次提交与远端 `main`（后端历史）**无共同祖先** → PR 提示 *There isn’t anything to compare*。

**方案**：`rebase --onto origin/main --root`（把“从根开始的整条历史”平移到主线尾部）。
- 冲突（.gitignore / README.md）类型：**add/add**。处理：`--ours` 取主线作基，再**追加**前端忽略与说明 → `git add` → `git rebase --continue`。
- rebase 后需 `git push -f origin feat/front-mws-phase1`（重写了历史，必须强推**功能分支**，禁止对 main 强推）。
- PR：`base=main` / `compare=feat/front-mws-phase1` → CI → **Squash and merge**。
- 合并后：本地 `main` 对齐远端：`git reset --hard origin/main`；设置拉取策略：`git config pull.ff only`（或 `pull.rebase true`）。

**心智图**：
- Git 本质是 **DAG**，PR 需要**共同祖先**。
- 选 `rebase --onto` 的目的：**干净 PR diff**、主线历史简洁。
- `--ours/--theirs` 在 rebase 语境下的含义易反：**ours=目的地（主线）**，**theirs=补丁（你的提交）**。

---

## 7. 下一阶段建议（短冲刺）
1) **真接口 A**：`GET /snapshot/inventory`（首页数据源）
   - PG 查询汇总 qty、Top2 库位、最早到期；返回与前端一致的 DTO。
   - 前端通过 env 开关对这个接口切真实 API，其它仍 MSW。
2) **真接口 B**：`POST /outbound/commit`（幂等 + 记账）
   - 幂等键（ref,item_id）；写 `moves`；可选 FEFO 扣批。
3) **表结构（若未完全落地）**：`moves`、`batches`、`stock_by_batch`；自检 `stocks == Σmoves`。
4) **前端小增强**：Tasks 支持 `接单/完成`（PATCH `/tasks/:id/status`），Batches 加临期筛选，Moves 导出 CSV。

---

## 8. 快捷指令清单（复用）
```bash
# 开发（MSW）
printf "VITE_USE_MSW=1\nVITE_API_URL=\n" > .env.development
pnpm dev

# MSW SW 文件
npx msw init public --save

# 自检
bash tools/selfcheck_phase1_to_2.sh
bash tools/selfcheck_phase2_shells.sh

# Git（rebase onto 主线）
git fetch origin
git rebase --onto origin/main --root
# 解决冲突 -> git add ... -> git rebase --continue
# 完成后强推功能分支
git push -u origin feat/front-mws-phase1 -f

# 合并后本地主线对齐
git checkout main && git reset --hard origin/main
```

---

### 附：排障“红黄灯”对照表
- **MSW off / Failed to fetch** → 确认 `main.tsx` 启动逻辑 + `.env.development` + `public/mockServiceWorker.js`。
- **Unexpected token '<'** → handlers 未命中：改用 `*/path` 通配；`api.ts` 保证相对路径；强刷两次。
- **首屏仍空** → `SnapshotPage` 重试/刷新；或导航切换后返回触发再拉取。

---

> 本页作为“从上次 Canvas 之后”的完整续聊纪要，可直接作为 PR 描述、开发交接或回溯依据。后续如进入后端联调阶段，可在此页继续增量记录接口契约与测试要点。
