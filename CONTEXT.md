# Knowledge Ingestion

Ingests information from multiple personal sources (email, notes, attachments) into a queryable knowledge graph, keeping every fact traceable back to where it came from.

## Language

**Pipeline**:
The deterministic orchestration engine that runs each Evidence item through a sequence of Steps (Convert, then Extract), tracking per-item progress internally so a failure resumes at the last completed Step instead of restarting. The Pipeline itself is plain, reusable infrastructure with no awareness of LLMs — only specific Steps happen to call one. Canonicalization is not its own Step — it's a tool the Agent calls per-entity during Extract (see Canonicalization) — and neither is Write: Convert writes the mechanical Evidence tree itself, while Extract's Agent performs Knowledge/Mention writes itself as part of its reasoning.
_Avoid_: Workflow, Orchestrator

**Step**:
An atomic, resumable unit of work within the Pipeline (Convert, Extract). Steps are shared across every Connector and content type — a Connector only supplies raw content; everything downstream of it is source-agnostic and reusable.
_Avoid_: Stage, Task, Canonicalize/Write as Steps (see Pipeline)

**Agent**:
The LLM-driven reasoning component behind judgment-requiring Steps (image captioning, Canonicalization's reuse-vs-create decision, Knowledge extraction). Where a Step needs to write to the graph, the Agent performs that write itself by calling the MCP's tools directly — the Agent is the seam between semantic judgment and mechanical graph writes, not the Pipeline. Tested independent of any specific graph MCP, against a fake/generic tool surface. Backed by a local, self-hosted llama.cpp server (OpenAI-compatible tool-calling API, vision-capable model) — see ADR 0002 — not a hosted cloud API.
_Avoid_: Model, LLM (the Agent is the reasoning role; the LLM is just what powers it)

**Connector**:
The generic component that turns the Sink's filesystem structure into a normalized Evidence content tree — directory nesting and sort order become `CONTAINED_IN` and position for free. There is exactly one Connector implementation, `FilesystemConnector` (see ADR 0003); it's what the Pipeline actually polls. It owns its own checkpoint state internally (which sink paths it's already handed off), independent of any Importer's checkpoint and independent of the graph MCP surface, which the ingestor doesn't control.
_Avoid_: Source, Adapter, Integration

**Importer**:
A pluggable, source-specific fetcher (Gmail, Keep, Google Drive, etc.) that talks to one external API — via whichever trigger mechanism fits that source, push or polling — and materializes new content into the Sink: one directory per item, a `_evidence.json` sidecar recording `kind` and `source_ref` (the pointer back to the origin system — "connecting the trail"), and child files as flat attachments. An Importer owns its own checkpoint against *its API* (e.g. "newest Gmail historyId seen") and has no tree-building responsibility at all — that's the Connector's job, shared across every Importer (see ADR 0003).
_Avoid_: Connector (an Importer doesn't yield an Evidence tree, so it isn't one)

**Sink**:
The shared filesystem directory that every Importer writes into and the one Connector reads from — the interchange point that lets N Importers reuse one Connector's tree-building instead of each building its own.
_Avoid_: Staging area, Buffer

**Evidence**:
A record of a raw source artifact — an email, a note, an attachment, a slide image — with a pointer back to where it lives (e.g. Gmail message ID, file path). Captures provenance, not meaning. Every node in a source's content tree (container, file, image, text snippet) is its own Evidence record — not just the top-level item — linked to its parent via `CONTAINED_IN`.
_Avoid_: Source, Document (when referring to the graph node)

**CONTAINED_IN**:
A structural edge from a child Evidence node to its parent container, carrying a `position` property so order (e.g. "the 2nd file's 1st image") is queryable directly from the graph.
_Avoid_: CONTAINS (rejected — direction goes child→parent, not parent→child)

**Conversion**:
The pipeline step that turns a raw Evidence node's bytes into ingestable content (via markitdown/docling), and may discover new structure in the process (e.g. a slide deck's individual slides, each with their own text and image, or an archive's individual entries). Every discovered piece becomes its own Evidence node — intermediate results are never discarded, only chained, and cascade through further Conversion (an archive containing a slide deck gets both unwrapped in turn). For images specifically, conversion produces a text description (OCR for literal text, vision captioning for visual/diagrammatic content) so later stages only ever reason over text, never branching on media type. Archive expansion reuses the same directory-tree-building code the Connector uses to read the Sink (see ADR 0004) — one implementation of "turn a directory into an Evidence tree," pointed at either the Sink or a temp-extracted archive.
_Avoid_: Extraction (reserved for the later step that turns Evidence into Knowledge)

**Canonicalization**:
Before minting a new Knowledge node, the ingestor runs a deterministic search (name/alias similarity, not an LLM call) over existing nodes of that type and surfaces any near-miss candidates ("you're adding Nikos, but there's already a Nick") into the extraction prompt. The search is deterministic and reproducible; the reuse-vs-create decision itself stays a judgment call made by the extraction step, now informed rather than blind.
_Avoid_: Entity resolution (used elsewhere for this general problem; Canonicalization is our term for how we approach it)

**Knowledge**:
A distilled entity, fact, or relationship extracted from Evidence — the semantic nodes and edges that make up the queryable graph itself.
_Avoid_: Fact, Entity (as a synonym for the whole category)

**Mention**:
A node representing one ingestion run's extraction from a single piece of Evidence. Connects once to that Evidence and fans out to every Knowledge node/edge it touched, giving provenance a traceable path without a direct edge per fact. Also the natural home for extraction metadata (confidence, model, timestamp).
_Avoid_: Extraction, Assertion, Observation

**EventBus**:
The async-safe, in-process publish/subscribe observers watch to see what the ingestor is doing live — Step lifecycle, item discovery, Agent activity. No persistence: a subscriber only ever sees events published while it's connected (live-tail), never a backlog. Publishers (Pipeline, Connector, Importer, Agent) never know or care whether anyone's listening — a subscriber-less EventBus is a safe no-op. Exposed externally as Server-Sent Events over HTTP, unauthenticated and bound to the local/trusted network only (see ADR 0002's reasoning) — event payloads may include snippets of real content, so this is a deliberate scope limit, not an oversight.
_Avoid_: Logger, Message queue (no persistence, no delivery guarantees beyond "currently connected")
