# ingestor

Event-based personal knowledge ingestion: watches configured sources (starting
with Gmail) and feeds what arrives into a knowledge graph, keeping every fact
traceable back to its source. See `CONTEXT.md` for the domain model and
`docs/adr/` for the architectural decisions behind it.

## First-time setup: Google OAuth

Gmail and Drive are both official Google APIs, so they share one OAuth
consent step and one token file (see `ingestor/google_auth.py`):

1. In the [Google Cloud Console](https://console.cloud.google.com/), create
   a project (if you don't have one), enable the Gmail API and Drive API,
   then create an OAuth client of type **Desktop app** and download its
   `client_secret.json`.
2. Run the one-time consent flow, pointing it at that file and at where you
   want the resulting token written — this opens a browser for you to
   approve access once, covering both Gmail and Drive:
   ```
   mkdir -p config
   uv run python -m ingestor.setup_google_auth /path/to/client_secret.json config/token.json
   ```
3. That's it — `docker-compose.yml` already mounts `./config` into the
   `ingestor` service and points `GOOGLE_TOKEN_PATH` at `config/token.json`.

`config/` is gitignored — never commit `client_secret.json` or `token.json`.

## Configuring sources

By default, Gmail ingests the whole inbox. Set either (or both) to scope it
down — `GMAIL_LABEL` to a label name (not Gmail's internal label id; it's
resolved for you), `GMAIL_QUERY` to a Gmail search string (the same syntax
as Gmail's own search box, e.g. `from:someone@example.com newer_than:7d`).

## Running

```
cp .env.example .env   # fill in NEO4J_PASSWORD, MODEL_FILE
docker compose up
```

The Agent talks to a local llama.cpp server (tool-calling, vision-capable
model) rather than a hosted API — see ADR 0002. If you already have a
llama.cpp instance running elsewhere, omit the `llamacpp` service and point
`LLAMACPP_BASE_URL` at it instead.

## Development

```
uv sync
uv run pytest        # full suite
uv run mypy           # typecheck
```

Tests are split across three seams (see the PRD in issue #1 for the
reasoning):

- `tests/seam1` — deterministic Connector/Pipeline orchestration. No LLM, no
  MCP; runs anywhere.
- `tests/seam2` — Agent reasoning. Requires a running llama.cpp server
  (`LLAMACPP_BASE_URL`, default `http://localhost:8080/v1`).
- `tests/seam3` — graph MCP contract. Requires `docker compose up -d neo4j
  neo4j-mcp` (`GRAPH_MCP_URL`, default `http://localhost:8000/mcp/`).
