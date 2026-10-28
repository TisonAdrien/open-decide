PYTHON_EXTRAS := --extra dev --extra ingest

.PHONY: help install format format-check lint type test test-tamev run clean docker-build docker-run

help:           ## Show this help
	@awk 'BEGIN {FS = ":.*?##"} /^[a-zA-Z_-]+:.*?##/ {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:        ## Install dev + ingest dependencies
	uv sync $(PYTHON_EXTRAS)

format:         ## Format code and auto-fix lint
	uv run $(PYTHON_EXTRAS) ruff format src tests
	uv run $(PYTHON_EXTRAS) ruff check --fix src tests

format-check:   ## Check formatting without modifying files
	uv run $(PYTHON_EXTRAS) ruff format --check src tests

lint:           ## Lint (no auto-fix)
	uv run $(PYTHON_EXTRAS) ruff check src tests

type:           ## Type-check with mypy
	uv run $(PYTHON_EXTRAS) mypy src

test:           ## Run unit tests
	uv run $(PYTHON_EXTRAS) pytest -q

test-tamev:     ## Run TAMEV integration tests (downloads ~90 MB, needs '.[tamev]')
	OPEN_DECIDE_TEST_TAMEV=1 uv run $(PYTHON_EXTRAS) pytest tests/test_backends_tamev.py -v

run:            ## Run the dev server (WSL-friendly)
	-WATCHFILES_FORCE_POLLING=true uv run $(PYTHON_EXTRAS) uvicorn open_decide.api.main:app --reload

run-bench:      ## Run without reload (model stays in memory)
	-uv run $(PYTHON_EXTRAS) uvicorn open_decide.api.main:app --host 127.0.0.1 --port 8000

clean:          ## Remove caches and build artifacts
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache dist build *.egg-info .coverage htmlcov

docker-build:   ## Build the Docker image
	docker build -t open-decide:latest .

docker-run:     ## Run the Docker image on port 8000
	docker run --rm -p 8000:8000 open-decide:latest
