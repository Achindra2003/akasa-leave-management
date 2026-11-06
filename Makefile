.PHONY: up down db test lint e2e eval dev-api dev-web types

up:        ## Run the whole stack (http://localhost:8000)
	docker compose up --build
down:
	docker compose down
db:        ## Only Postgres (for local dev / tests)
	docker compose up -d db
test: db   ## Backend unit + integration tests (real Postgres)
	cd backend && uv run pytest -q
lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && npm run typecheck
eval:      ## Agent golden-set evals (offline by default; set LLM_* for a live model)
	cd backend && uv run python -m evals.run_evals
e2e:       ## Browser smoke test against a running stack
	uv run --project backend python e2e/smoke.py http://localhost:8000 docs/screenshots
dev-api: db
	cd backend && uv run alembic upgrade head && uv run python run_dev.py
dev-web:
	cd frontend && npm run dev
types:     ## Regenerate frontend API types from the backend OpenAPI schema
	cd backend && uv run python -c "import json;from app.main import app;print(json.dumps(app.openapi()))" > ../frontend/openapi.json
	cd frontend && npm run gen:api
