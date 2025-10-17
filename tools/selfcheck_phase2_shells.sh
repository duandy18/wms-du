#!/usr/bin/env bash
set -euo pipefail
GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; BOLD="\033[1m"; NC="\033[0m"
ok(){ printf "${GREEN}✔${NC} %s\n" "$*"; }
fail(){ printf "${RED}✘ %s${NC}\n" "$*"; }
info(){ printf "${YELLOW}ℹ${NC} %s\n" "$*"; }

ROOT="${1:-$(pwd)}"
cd "$ROOT" || { fail "cannot cd into $ROOT"; exit 1; }

REQ=(
  "src/pages/TasksPage.tsx"
  "src/pages/BatchesPage.tsx"
  "src/pages/MovesPage.tsx"
  "src/mocks/handlers/tasks.ts"
  "src/mocks/handlers/batches.ts"
  "src/mocks/handlers/moves.ts"
)
echo -e "${BOLD}== File presence (Phase2 shells) ==${NC}"
PASS=1
for f in "${REQ[@]}"; do
  [[ -f "$f" ]] && ok "$f" || { fail "missing: $f"; PASS=0; }
done

echo -e "\n${BOLD}== handlers index exports ==${NC}"
if grep -q "from './tasks'" src/mocks/handlers/index.ts; then ok "export tasks"; else fail "export tasks missing"; PASS=0; fi
if grep -q "from './batches'" src/mocks/handlers/index.ts; then ok "export batches"; else fail "export batches missing"; PASS=0; fi
if grep -q "from './moves'" src/mocks/handlers/index.ts; then ok "export moves"; else fail "export moves missing"; PASS=0; fi

echo -e "\n${BOLD}== routes present ==${NC}"
if grep -q 'path="/tasks"' src/router.tsx; then ok "/tasks"; else fail "route /tasks"; PASS=0; fi
if grep -q 'path="/batches"' src/router.tsx; then ok "/batches"; else fail "route /batches"; PASS=0; fi
if grep -q 'path="/moves"' src/router.tsx; then ok "/moves"; else fail "route /moves"; PASS=0; fi

echo -e "\n${BOLD}== msw browser bootstrap ==${NC}"
if grep -q "setupWorker" src/mocks/browser.ts 2>/dev/null; then ok "setupWorker ready"; else info "browser.ts missing setupWorker (dev only)"; fi

echo -e "\n${BOLD}== Summary ==${NC}"
if [[ $PASS -eq 1 ]]; then
  echo -e "${GREEN}${BOLD}Phase 2 shells checks passed ✅${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}Some checks failed. See above. ❌${NC}"
  exit 2
fi
