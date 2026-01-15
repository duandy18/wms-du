# ==============================
#   WMS-DU Makefile (Thin Root)
# ==============================

SHELL := /bin/bash
VENV  := .venv
PY    := $(VENV)/bin/python
PIP   := $(VENV)/bin/pip
ALEMB := $(PY) -m alembic
PYTEST:= $(VENV)/bin/pytest

# ========================
# Database DSN
# ========================
TEST_DB_DSN := postgresql+psycopg://postgres:wms@127.0.0.1:55432/postgres
DEV_DB_DSN  := postgresql+psycopg://wms:wms@127.0.0.1:5433/wms
DEV_TEST_DB_DSN := postgresql+psycopg://wms:wms@127.0.0.1:5433/wms_test

# ---- 自动加载 .env.local ----
ifneq (,$(wildcard .env.local))
include .env.local
endif

# ---- 分模块拆分 ----
include scripts/make/env.mk
include scripts/make/db.mk
include scripts/make/audit.mk
include scripts/make/test.mk
include scripts/make/lint.mk
