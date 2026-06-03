# Contributing

DevLink is currently a backend-focused portfolio project. Keep changes scoped to
the active phase and avoid adding frontend, OAuth, or unrelated social features
unless the task explicitly asks for them.

## Local Setup

Start the required services:

```bash
docker compose up -d postgres redis
docker compose ps
```

Create a local `.env` from the example:

```bash
cp .env.example .env
```

Apply migrations:

```bash
cd backend
make migrate
```

If your local PostgreSQL volume does not include the test database, create it
once:

```bash
docker exec devlink-starter-postgres-1 psql -U devlink -d devlink -c "CREATE DATABASE devlink_test;"
```

## Development Commands

Run commands from `backend/`:

```bash
make format
make lint
make test
make run
```

Equivalent direct commands:

```bash
../.venv/bin/ruff format app
../.venv/bin/ruff check app
../.venv/bin/python -m pytest --cov=app -v
../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Code Guidelines

- Keep FastAPI endpoints thin: validate input, resolve dependencies, call
  services, and return response models.
- Put business logic in `app/services`.
- Use SQLAlchemy ORM and Alembic migrations for schema changes.
- Do not commit secrets or `.env`.
- Add or update tests for behavior changes.
- Run formatting, linting, and tests before pushing.

## Pull Request Checklist

- Scope is limited to the requested phase or bug fix.
- `make format`, `make lint`, and `make test` pass.
- New database fields include an Alembic migration.
- README or API examples are updated when behavior changes.
