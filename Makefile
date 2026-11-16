.PHONY: demo stop clean logs test init

## Start all agents + dashboard (builds images if needed)
demo:
	docker compose up --build

## Start in detached mode (background)
demo-d:
	docker compose up --build -d

## Stop all containers
stop:
	docker compose down

## Stop and remove volumes (full reset — deletes qdrant_store and state.db)
clean:
	docker compose down -v
	rm -rf infra/qdrant_store infra/state.db infra/state.db-wal infra/state.db-shm

## Tail orchestrator + dashboard logs
logs:
	docker compose logs -f dashboard

## Run IAA unit tests (no API key needed)
test:
	cd IAA && python -m pytest test_iaa.py -v

## Initialise data layer locally (no Docker)
init:
	python data/init_db.py
