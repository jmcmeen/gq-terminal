# gq-terminal — common development tasks.
# Most targets shell out to `uv` for fast, reproducible installs.
# Install uv once with:  curl -LsSf https://astral.sh/uv/install.sh | sh

.PHONY: help install dev sync lock test test-cov lint format typecheck check build clean

UV ?= uv

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | \
		awk -F ':.*## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (no dev deps) into the project venv.
	$(UV) sync --no-dev

dev: ## Install with dev dependencies (default for contributors).
	$(UV) sync --extra dev

sync: dev ## Alias for `make dev`.

lock: ## Regenerate uv.lock from pyproject.toml.
	$(UV) lock

test: ## Run the test suite.
	$(UV) run pytest

test-cov: ## Run tests with a coverage report.
	$(UV) run pytest --cov=gq_terminal --cov-report=term-missing

lint: ## Check formatting and lint without making changes.
	$(UV) run ruff check src tests
	$(UV) run black --check src tests

format: ## Auto-format and auto-fix lint issues.
	$(UV) run ruff check --fix src tests
	$(UV) run black src tests

typecheck: ## Run mypy.
	$(UV) run mypy src

check: lint typecheck test ## Run everything CI runs.

build: clean ## Build sdist and wheel into dist/.
	$(UV) run python -m build
	$(UV) run twine check dist/*

clean: ## Remove build/test artifacts.
	rm -rf dist/ build/ *.egg-info src/*.egg-info \
	       .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
