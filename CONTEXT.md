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
A pluggable adapter for one external source (Gmail, Keep, a folder, etc.), responsible for detecting new/changed content — via whichever trigger mechanism fits that source, push or polling — and yielding it as a normalized content tree. Each Connector owns its own checkpoint state internally (e.g. "newest Gmail message ID seen") rather than storing it in the graph: this bookkeeping must be fully automatic and reliable on its own, independent of the graph MCP surface, which the ingestor doesn't control.
_Avoid_: Source, Adapter, Integration

**Evidence**:
A record of a raw source artifact — an email, a note, an attachment, a slide image — with a pointer back to where it lives (e.g. Gmail message ID, file path). Captures provenance, not meaning. Every node in a source's content tree (container, file, image, text snippet) is its own Evidence record — not just the top-level item — linked to its parent via `CONTAINED_IN`.
_Avoid_: Source, Document (when referring to the graph node)

**CONTAINED_IN**:
A structural edge from a child Evidence node to its parent container, carrying a `position` property so order (e.g. "the 2nd file's 1st image") is queryable directly from the graph.
_Avoid_: CONTAINS (rejected — direction goes child→parent, not parent→child)

**Conversion**:
The pipeline step that turns a raw Evidence node's bytes into ingestable content (via markitdown/docling), and may discover new structure in the process (e.g. a slide deck's individual slides, each with their own text and image). Every discovered piece becomes its own Evidence node — intermediate results are never discarded, only chained. For images specifically, conversion produces a text description (OCR for literal text, vision captioning for visual/diagrammatic content) so later stages only ever reason over text, never branching on media type.
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
