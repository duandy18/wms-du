#!/usr/bin/env bash
set -euo pipefail

GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BOLD="\033[1m"; NC="\033[0m"
ok(){ printf "${GREEN}✔${NC} %s\n" "$*"; }
fail(){ printf "${RED}✘ %s${NC}\n" "$*"; }
info(){ printf "${YELLOW}ℹ${NC} %s\n" "$*"; }

ROOT="${1:-$(pwd)}"
cd "$ROOT" || { fail "cannot cd into $ROOT"; exit 1; }

REQ_FILES=(
  "src/pages/SnapshotPage.tsx"
  "src/pages/InboundPage.tsx"
  "src/pages/PutawayPage.tsx"
  "src/pages/OutboundPage.tsx"
  "src/pages/tools/StockToolPage.tsx"
  "src/pages/tools/LedgerToolPage.tsx"
  "src/components/common/ApiBadge.tsx"
  "src/components/snapshot/TileCard.tsx"
  "src/components/snapshot/InventoryDrawer.tsx"
  "src/lib/api.ts"
  "src/lib/csv.ts"
  "src/types/inventory.ts"
  "src/mocks/handlers/snapshot.ts"
  "src/mocks/handlers/outbound.ts"
  "src/mocks/handlers/index.ts"
  "src/router.tsx"
)

PASS=1

echo -e "${BOLD}== File presence ==${NC}"
for f in "${REQ_FILES[@]}"; do
  if [[ -f "$f" ]]; then ok "$f"; else fail "missing: $f"; PASS=0; fi
done

echo -e "\n${BOLD}== Router entries (6) ==${NC}"
declare -A ROUTES=(
  ["/"]="SnapshotPage"
  ["/inbound"]="InboundPage"
  ["/putaway"]="PutawayPage"
  ["/outbound"]="OutboundPage"
  ["/tools/stock"]="StockToolPage"
  ["/tools/ledger"]="LedgerToolPage"
)
if [[ -f src/router.tsx ]]; then
  for p in "${!ROUTES[@]}"; do
    if grep -q "path=\"${p}\"" src/router.tsx; then ok "route ${p} present"; else fail "route ${p} not found"; PASS=0; fi
  done
else
  fail "src/router.tsx not found"
  PASS=0
fi

echo -e "\n${BOLD}== MSW handlers sanity ==${NC}"
if grep -q "snapshotHandlers" src/mocks/handlers/snapshot.ts; then ok "snapshotHandlers exported"; else fail "snapshotHandlers missing"; PASS=0; fi
if grep -q "outboundHandlers" src/mocks/handlers/outbound.ts; then ok "outboundHandlers exported"; else fail "outboundHandlers missing"; PASS=0; fi
if grep -q "setupWorker" src/mocks/browser.ts; then ok "browser.ts has setupWorker"; else fail "browser.ts missing setupWorker"; PASS=0; fi

echo -e "\n${BOLD}== API/CVS helpers ==${NC}"
grep -q "export async function apiGet" src/lib/api.ts && ok "apiGet present" || { fail "apiGet missing"; PASS=0; }
grep -q "export async function apiPost" src/lib/api.ts && ok "apiPost present" || { fail "apiPost missing"; PASS=0; }
grep -q "export function toCSV" src/lib/csv.ts && ok "toCSV present" || { fail "toCSV missing"; PASS=0; }

echo -e "\n${BOLD}== Type definitions ==${NC}"
grep -q "export type InventoryTile" src/types/inventory.ts && ok "InventoryTile type present" || { fail "InventoryTile missing"; PASS=0; }

echo -e "\n${BOLD}== Optional: MSW bootstrapping in main.tsx ==${NC}"
if grep -q "worker.start" src/main.tsx 2>/dev/null; then
  ok "main.tsx calls worker.start (MSW)"
else
  info "main.tsx may not start MSW; if首次接入, 在 dev 模式加入：
  import { worker } from './mocks/browser';
  if (import.meta.env.DEV) { (window as any).__MSW_ENABLED__ = true; worker.start(); }"
fi

echo -e "\n${BOLD}== Summary ==${NC}"
if [[ $PASS -eq 1 ]]; then
  echo -e "${GREEN}${BOLD}All required checks passed ✅${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}Some checks failed. See above. ❌${NC}"
  exit 2
fi
