.PHONY: up down logs sh test

up:
	docker compose -f ops/compose/docker-compose.dev.yml up -d --build

down:
	docker compose -f ops/compose/docker-compose.dev.yml down

logs:
	docker compose -f ops/compose/docker-compose.dev.yml logs -f --tail=100

sh:
	docker compose -f ops/compose/docker-compose.dev.yml exec api bash

test:
	pytest -q || true
