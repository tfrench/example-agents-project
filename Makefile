setup:
	poetry env use python3.11
	poetry install

launch_ngrok:
	ngrok http http://localhost:8000

local_run:
	poetry run uvicorn aipolabs_test.api:app --reload --port 8000  # no load_balancer

run_tests:
	poetry run pytest --cov=aipolabs_test/ tests/test_api.py

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
