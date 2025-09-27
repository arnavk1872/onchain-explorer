.PHONY: help run test fmt lint clean install dev

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	uv sync

dev: ## Run development server
	uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run production server
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

test: ## Run tests
	uv run pytest tests/ -v

fmt: ## Format code with black and isort
	uv run black app/ tests/
	uv run isort app/ tests/

lint: ## Run linting checks
	uv run flake8 app/ tests/
	uv run mypy app/

clean: ## Clean up cache files
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
