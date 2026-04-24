# scripts/make/openapi.mk
# OpenAPI snapshot export (contract foundation)

.PHONY: openapi openapi-export

# Default target for humans/CI
openapi: openapi-export

openapi-export:
	$(PY) scripts/export_openapi.py --out openapi/_current.json
	cp openapi/_current.json openapi/v1.json
