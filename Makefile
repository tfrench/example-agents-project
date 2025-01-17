setup:
	poetry env use python3.11
	poetry install

launch_ngrok:
	ngrok http http://localhost:8000

run_local:
	poetry run uvicorn example_agents_project.api:app --reload --port 8000  # no load_balancer

run_tests:
	poetry run pytest -v --cov=example_agents_project/ tests/

run_ruff:
	poetry run ruff check . --fix

build:
	docker compose build

start:
	docker compose build
	docker compose up

stop:
	docker compose down -v

start_infra:
	docker compose up -d postgres redis

stop_infra:
	docker compose down -v postgres redis
