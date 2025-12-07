#!/usr/bin/env bash
# Phase 2.9 repo pruning & archiving helper (v3: strong-signal, router/schema protected)
# 安全默认：不运行 pytest，不访问数据库；仅静态扫描与清单。
#
# 用法：
#   bash scripts/phase2.9_prune.sh               # 计划模式（默认，不移动）
#   bash scripts/phase2.9_prune.sh --plan        # 同上
#   bash scripts/phase2.9_prune.sh --apply       # 执行移动（git mv）
#   bash scripts/phase2.9_prune.sh --with-cov=quick|services|both  # 可选覆盖率
#   bash scripts/phase2.9_prune.sh --days 60 --archive-root _archive
#
set -euo pipefail
export LC_ALL=C

# ---------- Config ----------
DAYS="${DAYS:-60}"
ARCHIVE_ROOT="${ARCHIVE_ROOT:-_archive}"
ARCH_LOC_EPOCH="${ARCHIVE_ROOT}/phase2.9_location_era"
ARCH_STALE="${ARCHIVE_ROOT}/phase2.9_stale"
BRANCH="${BRANCH:-chore/phase2.9-prune}"
COV_XML="${COV_XML:-coverage.xml}"

MODE="plan"             # plan | apply
WITH_COV="none"         # none | quick | services | both
PYTEST_ARGS="${PYTEST_ARGS:-}"

# 永久保留（强保护，任何情况下都不移动）
REQUIRED_KEEP=(
  "app/models"
  "app/db/base.py"
  "alembic/versions"
  "alembic/env.py"
  "tests"
  "scripts"
)

# 路由与 schemas 默认保护（只有“强命中”才可能被移动）
PROTECT_GLOBS=(
  "app/api/routers"
  "app/schemas"
)

NEEDED_CMDS=(git rg awk sed xargs sort uniq)

# ---------- Strong signals ----------
# 仅当文件匹配到“强信号”才认为是 location 时代遗留：
# - 直接字段：location_id
# - 直接 SQL：FROM/JOIN/INSERT locations
# - 显式模型/属性：Stock.location_id / models.location
# - 触发器/函数关键词
STRONG_GREP='(\blocation_id\b|FROM[[:space:]]+locations\b|JOIN[[:space:]]+locations\b|INSERT[[:space:]]+INTO[[:space:]]+locations\b|Stock\.location_id\b|models?\.location\b|CREATE[[:space:]]+TRIGGER\b|plpgsql\b|tg_op\b)'

# ---------- Args ----------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan) MODE="plan"; shift ;;
    --apply) MODE="apply"; shift ;;
    --with-cov=quick) WITH_COV="quick"; shift ;;
    --with-cov=services) WITH_COV="services"; shift ;;
    --with-cov=both) WITH_COV="both"; shift ;;
    --days) DAYS="$2"; shift 2 ;;
    --archive-root) ARCHIVE_ROOT="$2"; ARCH_LOC_EPOCH="${ARCHIVE_ROOT}/phase2.9_location_era"; ARCH_STALE="${ARCHIVE_ROOT}/phase2.9_stale"; shift 2 ;;
    --pytest-args) PYTEST_ARGS="$2"; shift 2 ;;
    -h|--help) sed -n '1,160p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ---------- Utils ----------
log()  { printf "\033[1;34m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }
die()  { err "$*"; exit 1; }

need_cmds() { for c in "${NEEDED_CMDS[@]}"; do command -v "$c" >/dev/null 2>&1 || die "缺少命令：$c"; done; }
in_repo()   { git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "当前目录不是 git 仓库"; }

ensure_branch() {
  local cur; cur="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$cur" != "$BRANCH" ]]; then
    if git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
      log "切换到已有分支 $BRANCH"; git switch "$BRANCH" >/dev/null
    else
      log "创建并切换到新分支 $BRANCH"; git switch -c "$BRANCH" >/dev/null
    fi
  fi
}

git_clean_check() {
  if [[ "$(git status --porcelain | wc -l)" -ne 0 ]]; then
    warn "工作区有未提交改动，建议先提交；脚本仍将继续。"
  fi
}

mkdirp() { mkdir -p "$ARCH_LOC_EPOCH" "$ARCH_STALE"; }

path_starts_with_any() {
  local f="$1"; shift
  for g in "$@"; do
    if [[ "$f" == "$g" || "$f" == "$g"* ]]; then return 0; fi
  done
  return 1
}

is_required_keep() { path_starts_with_any "$1" "${REQUIRED_KEEP[@]}"; }
is_protected_glob() { path_starts_with_any "$1" "${PROTECT_GLOBS[@]}"; }

do_move() {
  local src="$1" dst="$2"
  if is_required_keep "$src"; then log "保留（REQUIRED）：$src"; return 0; fi
  [[ -e "$src" ]] || { warn "文件不存在，跳过：$src"; return 0; }
  echo "git mv \"$src\" \"$dst/$(basename "$src")\""
  git mv "$src" "$dst/$(basename "$src")"
}

filter_required_and_protected() {
  # 仅对“强命中集合”进行：
  #  - 剔除 REQUIRED_KEEP
  #  - 对 PROTECT_GLOBS：如果文件强命中才允许（此函数的输入已经是强命中集合，所以这里允许通过）
  # 因此这里只需要剔除 REQUIRED_KEEP。
  local infile="$1"
  awk 'NF' "$infile" | while read -r f; do
    if is_required_keep "$f"; then
      continue
    fi
    echo "$f"
  done | sort -u
}

# ---------- Main ----------
need_cmds
in_repo
ensure_branch
git_clean_check
mkdirp

log "生成全量文件清单 ..."
git ls-files | sort -u > /tmp/all_files.txt

log "扫描 location 时代候选（宽信号：location / trigger / plpgsql 等）……"
rg -n "\blocation(_id)?\b|CREATE TRIGGER|plpgsql|tg_op" app tests alembic \
  | awk -F: '{print $1}' | sort -u > /tmp/location_residue_wide.txt || true
grep -v '^alembic/versions/' /tmp/location_residue_wide.txt | sort -u > /tmp/location_residue.txt || true
log "宽命中数量：$(wc -l < /tmp/location_residue.txt)"

log "收紧为强命中集合（必须含列名/显式 SQL/显式模型/触发器词）……"
rg -n -P "$STRONG_GREP" app tests alembic \
  | awk -F: '{print $1}' | sort -u > /tmp/location_residue_strong_raw.txt || true
# 排除迁移历史
grep -v '^alembic/versions/' /tmp/location_residue_strong_raw.txt | sort -u > /tmp/location_residue_strong.txt || true
log "强命中数量：$(wc -l < /tmp/location_residue_strong.txt)"

# 统计受保护目录中的强命中情况（仅用于提示）
for g in "${PROTECT_GLOBS[@]}"; do
  c=$(grep -E "^${g}(/|$)" /tmp/location_residue_strong.txt | wc -l | awk '{print $1}')
  log "强命中（受保护目录）${g}: ${c}"
done

# 生成最终 location 移动清单：仅强命中，且剔除 REQUIRED_KEEP
filter_required_and_protected /tmp/location_residue_strong.txt > /tmp/move_location.txt
log "最终 location 移动数：$(wc -l < /tmp/move_location.txt)"

# ---- 覆盖率（可选）与“未变更天数” ----
> /tmp/zero_coverage.txt
if [[ "$WITH_COV" != "none" ]]; then
  NODES=""; CASES=""
  case "$WITH_COV" in
    quick)     CASES="tests/quick" ;;
    services)  CASES="tests/services" ;;
    both)      CASES="tests/quick tests/services" ;;
  esac
  log "运行覆盖率（$WITH_COV）……（可能较慢，可通过 --pytest-args 传入 -k 过滤）"
  set +e
  pytest -q -s --cov=app --cov-report=xml:"$COV_XML" $CASES $PYTEST_ARGS
  rc=$?; set -e
  if [[ $rc -ne 0 ]]; then
    warn "pytest 返回码：$rc；若未生成 coverage.xml，将跳过 0 覆盖分析。"
  fi
fi

if [[ -f "$COV_XML" ]]; then
  log "解析 coverage.xml，提取 0 覆盖 app 模块……"
  python - <<'PY' > /tmp/zero_coverage.txt
import xml.etree.ElementTree as ET, os
p="coverage.xml"
if os.path.exists(p):
    t=ET.parse(p)
    zero=set()
    for el in t.iter():
        fn=el.attrib.get('filename'); lr=el.attrib.get('line-rate')
        if not fn or not lr: continue
        try: rate=float(lr)
        except: continue
        if fn.startswith('app/') and abs(rate-0.0)<1e-12:
            zero.add(fn)
    print("\n".join(sorted(zero)))
PY
else
  log "未找到 coverage.xml，保持 0 覆盖清单为空。"
fi
log "0 覆盖文件：$(wc -l < /tmp/zero_coverage.txt)"

log "计算 ${DAYS} 天未变更的文件（纯 git 历史）……"
git log --since="${DAYS} days ago" --name-only --pretty=format: | sort -u > /tmp/changed_${DAYS}d.txt
sort -u /tmp/all_files.txt -o /tmp/all_files.txt
sort -u /tmp/changed_${DAYS}d.txt -o /tmp/changed_${DAYS}d.txt
comm -23 /tmp/all_files.txt /tmp/changed_${DAYS}d.txt > /tmp/stale_${DAYS}d.txt
log "未变更 ${DAYS} 天文件：$(wc -l < /tmp/stale_${DAYS}d.txt)"

log "交集：未变更 ∩ 0 覆盖 -> 候选冷宫集 ……"
sort -u /tmp/stale_${DAYS}d.txt -o /tmp/stale_${DAYS}d.txt
sort -u /tmp/zero_coverage.txt -o /tmp/zero_coverage.txt
comm -12 /tmp/stale_${DAYS}d.txt /tmp/zero_coverage.txt > /tmp/stale_and_zero.txt
log "候选冷宫文件：$(wc -l < /tmp/stale_and_zero.txt)"

# 冷宫最终清单（剔除 REQUIRED_KEEP；routers/schemas 本就很可能无 0 覆盖，不必特别对待）
awk 'NF' /tmp/stale_and_zero.txt | while read -r f; do
  if path_starts_with_any "$f" "${REQUIRED_KEEP[@]}"; then continue; fi
  echo "$f"
done | sort -u > /tmp/move_stale.txt
log "最终 冷宫 移动数：$(wc -l < /tmp/move_stale.txt)"

echo "-------------------------------------------"
echo "产出文件："
echo "  /tmp/location_residue.txt           # 宽命中（参考）"
echo "  /tmp/location_residue_strong.txt    # 强命中（用于移动）"
echo "  /tmp/move_location.txt              # 最终：基于强命中 + 剔除永久保留"
echo "  /tmp/zero_coverage.txt              # 0 覆盖 app 模块（若启用覆盖率或已有 coverage.xml）"
echo "  /tmp/stale_${DAYS}d.txt             # ${DAYS} 天未变更"
echo "  /tmp/move_stale.txt                 # 最终：0 覆盖 ∩ 未变更 ∩ 非永久保留"
echo "-------------------------------------------"

if [[ "$MODE" = "apply" ]]; then
  log "执行归档移动（git mv）……"
  moved=0
  while read -r f; do
    [[ -z "${f:-}" ]] && continue
    do_move "$f" "$ARCH_LOC_EPOCH" && ((moved++)) || true
  done < /tmp/move_location.txt

  while read -r f; do
    [[ -z "${f:-}" ]] && continue
    grep -qxF "$f" /tmp/move_location.txt 2>/dev/null && continue
    do_move "$f" "$ARCH_STALE" && ((moved++)) || true
  done < /tmp/move_stale.txt

  log "完成移动：${moved} 个文件。"
  log "建议提交：git commit -m 'chore(phase2.9): archive location-era & stale zero-cov files'"
else
  log "计划模式：未移动任何文件。若要执行移动，请使用 --apply。"
fi
