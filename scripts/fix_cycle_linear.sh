#!/usr/bin/env bash
set -euo pipefail

# 自动探测迁移目录（同时兼容两套常见路径）
VERS_DIRS=""
[ -d app/db/migrations/versions ] && VERS_DIRS="$VERS_DIRS app/db/migrations/versions"
[ -d alembic/versions ] && VERS_DIRS="$VERS_DIRS alembic/versions"
if [ -z "$VERS_DIRS" ]; then
  echo "❌ 没找到迁移目录（app/db/migrations/versions 或 alembic/versions）"
  exit 2
fi

# 目标链：子 → 父（把这 7 个 revision 串成单线）
pairs=(
  "2a01baddb001:31fc28eac057"
  "2a01baddb002:2a01baddb001"
  "3a_fix_sqlite_inline_pks:2a01baddb002"
  "1088800f816e:3a_fix_sqlite_inline_pks"
  "1f9e5c2b8a11:1088800f816e"
  "1223487447f9:1f9e5c2b8a11"
  "bdc33e80391a:1223487447f9"
)

# sed 兼容：macOS 用 gsed，Linux 用 sed
SED="sed -i"
command -v gsed >/dev/null 2>&1 && SED="gsed -i"

changed=0
for p in "${pairs[@]}"; do
  child="${p%%:*}"
  parent="${p##*:}"

  # 定位包含 revision="child" 的文件（内容匹配，不依赖文件名）
  file="$(grep -RIl --include="*.py" -E "^[[:space:]]*revision[[:space:]]*[:=][[:space:]]*['\"]${child}['\"]" ${VERS_DIRS} || true)"
  if [ -z "$file" ]; then
    echo "⚠️  未找到 revision=${child} 的文件（请确认它真的存在于上述迁移目录）"
    continue
  fi

  cp "$file" "$file.bak"
  # 统一把 down_revision 行重写成 down_revision = "parent"
  $SED -E "s/^[[:space:]]*down_revision[[:space:]]*[:=][[:space:]]*.*/down_revision = \"${parent}\"/" "$file"
  echo "✅ Patched ${child}: down_revision -> ${parent}   ($file)"
  changed=$((changed+1))
done

if [ "$changed" -eq 0 ]; then
  echo "ℹ️  没有改动（可能已经线性化，或 revision 不在这两个目录）"
else
  echo "🧩 已为 ${changed} 个迁移文件写入 .bak 备份"
fi

echo
echo "下一步："
echo "  1) alembic heads -v"
echo "  2) 如还有两个 head：alembic revision --merge -m \"merge heads\" <HEAD_A> <HEAD_B>"
echo "  3) 确保 warehouses/locations 迁移的 down_revision 指向第 2 步生成的合并修订（或唯一 head）"
echo "  4) alembic upgrade head && pytest -q -m smoke"
