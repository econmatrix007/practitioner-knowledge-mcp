# practitioner-knowledge-mcp: common tasks.
# Run `make help` to list targets. Every target runs inside the uv-managed .venv.

PYTHON_VERSION ?= 3.12
UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help install hooks lint format test guard check clean

help: ## List available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install: ## Create .venv and install the package plus dev tools
	$(UV) sync --python $(PYTHON_VERSION)

hooks: ## Install git pre-commit hooks for this clone
	$(UV) run pre-commit install

lint: ## Check code style (no changes made)
	$(UV) run ruff check .
	$(UV) run ruff format --check .

format: ## Auto-fix code style
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test: ## Run the test suite
	$(UV) run pytest

# Minimal guard until scripts/check_private.sh lands in Phase 7.
guard: ## Fail if private or database files are tracked by git
	@bad=$$(git ls-files | grep -E '(^|/)(HANDOFF\.md|\.private-terms\.txt|\.env)$$|\.(db|sqlite|sqlite3)$$|^data/' || true); \
	if [ -n "$$bad" ]; then echo "Tracked private files:"; echo "$$bad"; exit 1; fi; \
	echo "guard: no private files tracked"

check: guard lint test ## Run every check; must pass before each commit
	$(UV) run pre-commit run --all-files

clean: ## Remove caches and build output (keeps .venv and your data)
	rm -rf .pytest_cache .ruff_cache build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
