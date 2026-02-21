# scripts/make/openapi.mk
# OpenAPI snapshot export (contract foundation)

.PHONY: openapi-export openapi-export-dev

openapi-export:
	$(PY) scripts/export_openapi.py --out openapi/_current.json
	cp openapi/_current.json openapi/v1.json

openapi-export-dev:
	$(PY) scripts/export_openapi.py --enable-dev-routes --out openapi/_current.json
	cp openapi/_current.json openapi/v1.json
