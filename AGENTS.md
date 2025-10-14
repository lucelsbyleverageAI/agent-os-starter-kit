# Repository Guidelines

## Project Structure & Module Organization
- `apps/web/`: Next.js client; UI modules live under `src/` with shared primitives in `src/components/`.
- `apps/langconnect/`: FastAPI data plane with core services in `langconnect/` and pytest suites in `tests/`.
- `apps/mcp/`: Custom MCP server in `src/mcp_server/`, including tool adapters under `tools/` and entrypoints in `main.py`.
- `langgraph/src/agent_platform/`: LangGraph graphs and helpers; register new templates in `langgraph.json`.
- Infra and automation assets reside in `database/`, `supabase/`, and `scripts/`.

## Build, Test, and Development Commands
Run the full platform locally from the repo root:
```bash
make start-dev   # bootstrap Docker stack with hot reload
make stop        # stop app containers and background agents
```
Service-level workflows:
```bash
cd apps/web && yarn dev
cd apps/langconnect && poetry run uvicorn langconnect.server:APP --reload --port 8080
cd apps/mcp && poetry run mcp-server serve --reload
```

## Coding Style & Naming Conventions
- TypeScript: Prettier-managed 2-space indent; components in `PascalCase.tsx`, hooks/utilities in `camelCase.ts`. Run `yarn lint` and `yarn format:check` before committing.
- Python (LangConnect): Ruff-enforced 88-column style with `snake_case` functions and `CamelCase` classes. Run `poetry run ruff check langconnect` and `poetry run pytest`.
- Python (MCP & LangGraph): Format with Black/Isort (`poetry run black src`, `poetry run isort src`) and uphold type coverage via `poetry run mypy src`.

## Testing Guidelines
- Python services rely on `pytest` with async fixtures; name files `test_*.py` (see `apps/langconnect/tests/test_permission_service.py`). Run `poetry run pytest [--cov]` from each service directory.
- Frontend tests should live in `apps/web/src/__tests__/` as `*.test.ts(x)`; execute with your chosen runner (commonly `vitest`) and attach UI screenshots when visual changes ship.

## Commit & Pull Request Guidelines
- Use imperative commit subjects (optionally `type: subject`) and call out config or migration work in the body.
- PRs should summarise scope, list touched services (`web`, `langconnect`, `mcp`, `langgraph`), note risks, and document tests run. Request a domain reviewer and flag any database or Supabase updates.

## Security & Configuration Tips
- Copy `.env.local.example` to `.env.local` and keep Supabase keys, OpenAI tokens, and MCP secrets out of git.
- When adding tools or agents, synchronise scopes across LangConnect and the MCP server, and review `deployment_docs/` before promoting changes.
