# practitioner-knowledge-mcp: common tasks.
# Run `make help` to list targets. Every target runs inside the uv-managed .venv.

PYTHON_VERSION ?= 3.12
UV ?= uv
INSPECTOR ?= @modelcontextprotocol/inspector@2.9.0

.DEFAULT_GOAL := help
.PHONY: help install hooks lint format test guard check init-db seed run-stdio run-http inspect smoke clean

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

init-db: ## Create or upgrade the ideas database (KNOWLEDGE_MCP_DB or ~/.knowledge-mcp/ideas.db)
	$(UV) run python scripts/init_db.py

seed: ## Load the 12 fictional sample ideas (safe to run twice)
	$(UV) run python scripts/seed_db.py

run-stdio: ## Run the server over stdio (what Claude Desktop launches); Ctrl-C to stop
	$(UV) run knowledge-mcp --transport stdio

run-http: ## Run the HTTP server in this Terminal (127.0.0.1:8765 unless KNOWLEDGE_MCP_* set)
	$(UV) run knowledge-mcp --transport http

# The server defaults to stdio, so the Inspector gets a command with no flags to misparse.
inspect: ## Open MCP Inspector in your browser, connected to this server (needs Node.js)
	npx -y $(INSPECTOR) $(UV) run knowledge-mcp

smoke: ## Launch the server like Claude Desktop does and test every read-only tool
	$(UV) run python scripts/smoke_stdio.py

clean: ## Remove caches and build output (keeps .venv and your data)
	rm -rf .pytest_cache .ruff_cache build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
