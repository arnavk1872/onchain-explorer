.PHONY: help install dev build start lint clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies
	npm install

dev: ## Run development server
	npm run dev

build: ## Build for production
	npm run build

start: ## Start production server
	npm run start

lint: ## Run linting
	npm run lint

type-check: ## Run TypeScript type checking
	npm run type-check

clean: ## Clean build artifacts
	rm -rf .next
	rm -rf node_modules
