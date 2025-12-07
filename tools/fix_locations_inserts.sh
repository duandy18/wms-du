#!/usr/bin/env bash
set -euo pipefail

# 需求：GNU sed + ripgrep (rg)
# 作用：在 tests/ 下批量把 "INSERT INTO locations(id, ...)" 语句改为：
#       1) 尾部补 "ON CONFLICT (id) DO NOTHING"
#       2) 紧跟追加 "SELECT setval('public.locations_id_seq', (SELECT COALESCE(MAX(id),0)+1 FROM public.locations), false);"
# 仅处理 Python 测试文件（.py）

ROOT_DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "${ROOT_DIR}"

echo "[INFO] scanning files..."
MAPFILE=()
while IFS= read -r f; do
  # 只处理非 .bak 的 .py 文件
  if [[ "$f" == *.py && "$f" != *.bak ]]; then
    MAPFILE+=( "$f" )
  fi
done < <(rg -n "INSERT INTO locations\(" tests | cut -d: -f1 | sort -u)

if [[ ${#MAPFILE[@]} -eq 0 ]]; then
  echo "[WARN] no files matched."
  exit 0
fi

echo "[INFO] will patch ${#MAPFILE[@]} files"
for f in "${MAPFILE[@]}"; do
  echo "  >> patching $f"
  # 备份
  cp -f "$f" "$f.bak.fix-locations-id"

  # 情形一：INSERT INTO locations(id, name, warehouse_id) VALUES (...)
  # 在 VALUES(...) 末尾追加 ON CONFLICT 和 setval 语句（同一 text(""" ... """) 字符串内）
  sed -i -E \
    "s#(INSERT INTO locations\(id,\s*name,\s*warehouse_id\)\s*VALUES\s*\([^)]+\))#\1 ON CONFLICT (id) DO NOTHING; SELECT setval('public.locations_id_seq',(SELECT COALESCE(MAX(id),0)+1 FROM public.locations),false)#g" "$f"

  # 情形二：INSERT INTO locations(id, warehouse_id, name) VALUES (...)
  sed -i -E \
    "s#(INSERT INTO locations\(id,\s*warehouse_id,\s*name\)\s*VALUES\s*\([^)]+\))#\1 ON CONFLICT (id) DO NOTHING; SELECT setval('public.locations_id_seq',(SELECT COALESCE(MAX(id),0)+1 FROM public.locations),false)#g" "$f"

  # 情形三：INSERT INTO locations(id, warehouse_id, code, name) VALUES (...)（少见，但一并处理）
  sed -i -E \
    "s#(INSERT INTO locations\(id,\s*warehouse_id,\s*code,\s*name\)\s*VALUES\s*\([^)]+\))#\1 ON CONFLICT (id) DO NOTHING; SELECT setval('public.locations_id_seq',(SELECT COALESCE(MAX(id),0)+1 FROM public.locations),false)#g" "$f"

  # 情形四：INSERT INTO locations(id, name, warehouse_id) 换行写法（VALUES 与 INSERT 换行）
  # 捕获到 ) 后面立刻追加补丁
  sed -i -E \
    ":a;N;\$!ba;s#(INSERT INTO locations\(id,\s*name,\s*warehouse_id\)\s*[\r\n\t ]*VALUES\s*\([^)]+\))#\1 ON CONFLICT (id) DO NOTHING; SELECT setval('public.locations_id_seq',(SELECT COALESCE(MAX(id),0)+1 FROM public.locations),false)#g" "$f"

  sed -i -E \
    ":a;N;\$!ba;s#(INSERT INTO locations\(id,\s*warehouse_id,\s*name\)\s*[\r\n\t ]*VALUES\s*\([^)]+\))#\1 ON CONFLICT (id) DO NOTHING; SELECT setval('public.locations_id_seq',(SELECT COALESCE(MAX(id),0)+1 FROM public.locations),false)#g" "$f"
done

echo "[INFO] done. You can review diffs with: git -c color.ui=always diff | less -R"
