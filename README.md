# ingestor

Event-based personal knowledge ingestion: watches configured sources (starting
with Gmail) and feeds what arrives into a knowledge graph, keeping every fact
traceable back to its source. See `CONTEXT.md` for the domain model and
`docs/adr/` for the architectural decisions behind it.

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
