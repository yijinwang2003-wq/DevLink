.PHONY: test lint format migrate run

PYTHON ?= ../.venv/bin/python
RUFF ?= ../.venv/bin/ruff
ALEMBIC ?= ../.venv/bin/alembic
UVICORN ?= ../.venv/bin/uvicorn

test:
	$(PYTHON) -m pytest --cov=app -v

lint:
	$(RUFF) check app

format:
	$(RUFF) format app

migrate:
	$(ALEMBIC) upgrade head

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload
