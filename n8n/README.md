# n8n

## What this does

n8n is bundled as part of the stack and is run in Docker. We always pull the latest official n8n image and host it for you.

Alongside the main n8n container, there is a small one‑shot "import" service that, on startup, loads any workflows and credentials found in this repo and imports them into n8n. This lets us ship ready‑made templates that you (or other users) can start from.

Where this is defined:
- Local dev: `docker-compose.local.dev.yml` (`n8n` and `n8n-import` services)
- Production: `docker-compose.production.yml` (`n8n` and `n8n-import` services)

## Folder layout

- `n8n/data/workflows/` – JSON workflow templates auto‑imported on startup
- `n8n/data/credentials/` – JSON credential templates auto‑imported on startup

If these folders are empty, nothing is imported (the import service will simply skip).

## Helper scripts

- `scripts/export-n8n.sh` – Exports all workflows and/or credentials from the running local n8n container into `n8n/data/...` so they can be committed to the repo.
- `scripts/sanitise-n8n.js` – Cleans exported JSON (removes personal/project metadata) so templates are safe to share.

## Export with Make (recommended)

If you've saved workflows/credentials in your local n8n instance, run:
```bash
make export-n8n
```

This will:
- Export all current workflows and credentials from the running `n8n` container to a temporary location inside the container
- Copy the exported files to `n8n/data/workflows/` and `n8n/data/credentials/` on your host
- Automatically sanitise the JSON to remove personal/project metadata

**Note:** The `/data/workflows` and `/data/credentials` directories are mounted as read-only inside the container to prevent accidental modifications during normal operation. The export script works around this by exporting to `/tmp` inside the container first, then copying the files out to your host machine.

Then remove any files you don't want to keep and commit the rest. On next startup, the import service will auto‑apply whatever is in `n8n/data/...`.

Typical usage (local dev):
```bash
# Start the full stack (includes n8n and the import step)
make start-dev

# After editing in the n8n UI, export your changes back into the repo
make export-n8n                    # or ./scripts/export-n8n.sh workflows|credentials
```



