# Agent OS - Development Environment Scripts

This directory contains the core Python scripts that manage the local development environment for the Agent OS platform. These scripts are designed to be run via the main `Makefile` in the project root, providing a simple and consistent interface for starting, stopping, and cleaning the entire stack.

## Orchestration Philosophy

The development environment is a hybrid setup designed for maximum productivity:

-   **Docker for Infrastructure**: Core infrastructure services that are stable and don't require frequent code changes (like Supabase, n8n, and Windmill) are run in Docker via `docker-compose.local.dev.yml`.
-   **Local Processes for Active Development**: Services under active development (`LangGraph` and the `Web Frontend`) are run as local processes on the host machine. This enables hot-reloading, faster iteration, and easier debugging.
-   **Hot-Reloading in Docker**: For the backend Python services (`LangConnect` and `MCP Server`), the development Docker images are configured to mount the source code as a volume and run with a hot-reloading server (`uvicorn`), providing a seamless development experience even within containers.

The scripts in this directory automate the entire process of managing this hybrid environment.

## Scripts Overview

### `start_local_services.py`

This is the main entry point for starting the development stack. It orchestrates the following steps:

1.  **Prerequisite Checks**: Verifies that Docker is running and that all necessary dependencies (`docker-compose`, `poetry`, `yarn`) are installed.
2.  **Environment Loading**: Loads environment variables from the root `.env.local` file.
3.  **Docker Services**: Starts all infrastructure services defined in `docker-compose.local.dev.yml` in detached mode (`-d`). This includes Supabase, n8n, Windmill, and the hot-reloading containers for LangConnect and the MCP Server.
4.  **Health Checks**: Waits for the core Docker services to become healthy before proceeding.
5.  **Local Services**:
    -   Installs dependencies for the `langgraph` and `apps/web` directories using `poetry install` and `yarn install`.
    -   Starts the LangGraph development server (`poetry run langgraph dev`) as a background process.
    -   Starts the Web Frontend development server (`yarn dev`) as a background process.
6.  **Monitoring**: The script remains active, monitoring the health of the local processes and providing a consolidated view of all service URLs. When the script is terminated (e.g., with `Ctrl+C`), it automatically triggers a cleanup to stop all services.

**Usage:**

```bash
# Recommended method via Makefile
make start-dev

# Direct invocation
poetry run python scripts/start_local_services.py
```

**Options:**

-   `--skip-frontend`: Skip starting the Web Frontend.
-   `--skip-langgraph`: Skip starting the LangGraph server.

### `stop_local_services.py`

This script is responsible for completely stopping and cleaning the development environment. It can perform different levels of cleanup based on the provided flags.

1.  **Process Termination**: It first finds and terminates the local `LangGraph` and `Web Frontend` processes.
2.  **Docker Shutdown**: It then gracefully stops and removes all containers, networks, and (optionally) volumes defined in `docker-compose.local.dev.yml`.

**Usage:**

The script offers several cleanup modes, which are exposed via the `Makefile` for convenience.

| Makefile Command        | Direct Script Command                                       | Description                                                                                                                              |
| ----------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `make stop`             | `python scripts/stop_local_services.py`                     | **Standard Stop**: Stops all containers and local processes. Preserves all data in Docker volumes.                                       |
| `make clean-volumes`    | `python scripts/stop_local_services.py --clean-problematic` | **Clean Problematic Volumes**: A safe cleanup that stops everything and removes only the volumes known to cause startup issues (e.g., Windmill's cache), while preserving your main database. |
| `make clean`            | `python scripts/stop_local_services.py --remove-volumes`    | **Full Cleanup (Destructive)**: Stops everything and removes **ALL** Docker volumes. **This will delete your entire local database.**   |
| `make reset`            | `python scripts/stop_local_services.py --complete-reset`    | **Complete Reset (Most Destructive)**: The most aggressive cleanup. Force-removes all containers and volumes associated with the project. Use this as a last resort if you are facing persistent Docker-related issues. |

### `utils.py`

This is a utility module containing shared functions used by the start and stop scripts. It handles common tasks like:

-   Loading and parsing the `.env.local` file.
-   Running shell commands.
-   Finding and terminating processes by name.
-   Interacting with Docker Compose.
-   Checking for required dependencies.

## Troubleshooting

-   **Docker Startup Failures**: If `make start-dev` fails, especially after pulling new changes, the most common cause is a locked or corrupted Docker volume. The safest first step is to run `make clean-volumes`, which will resolve most issues without deleting your data.
-   **Persistent Docker Errors**: If `clean-volumes` doesn't help, `make reset` is the next step. This is a "sledgehammer" approach that will fix any underlying Docker state issues at the cost of your local data.
-   **Port Conflicts**: If a service fails to start, ensure that the ports listed in `docker-compose.local.dev.yml` (e.g., `8000`, `8080`, `3000`) are not already in use by another application on your machine.
-   **Stale Processes**: If you suspect a process from a previous run was not terminated correctly, `make stop` will find and kill any lingering development server processes.