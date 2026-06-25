VENV := backend/.venv
.DEFAULT_GOAL := help

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup-backend: ## Create venv + install backend dev dependencies
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r backend/requirements-dev.txt

setup-frontend: ## Install frontend dependencies
	cd frontend && npm install

setup: setup-backend setup-frontend ## Install everything

test: ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest -q

dev-backend: ## Run the API (demo mode, autoreload) on :8080
	cd backend && CF_FAKE=true .venv/bin/python -m uvicorn app.main:app --reload --port 8080

dev-frontend: ## Run the Vite dev server on :5173 (proxies /api to :8080)
	cd frontend && npm run dev

build-frontend: ## Build the SPA into frontend/dist
	cd frontend && npm run build

docker-build: ## Build the production container image
	docker build -t domainsentinel .

docker-run: ## Run the container on :8080 (demo mode)
	docker run --rm -p 8080:8080 domainsentinel

.PHONY: help setup setup-backend setup-frontend test dev-backend dev-frontend build-frontend docker-build docker-run
