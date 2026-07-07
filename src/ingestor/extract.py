from __future__ import annotations

from ingestor.evidence import EvidenceNode
from ingestor.pipeline import PipelineContext

EXTRACTION_SYSTEM_PROMPT = """\
You extract structured Knowledge from a single piece of Evidence text and \
write it into a Neo4j graph, using the tools available to you.

Graph schema you must follow:
- Knowledge nodes: label `Knowledge`, properties `id` (a short, unique, \
  slug-like identifier you choose), `name`, and `type` (e.g. Person, \
  Project, Concept, Decision). Use MERGE on `id`, never CREATE, so retries \
  don't duplicate a node.
- Relationships between Knowledge nodes: any UPPER_SNAKE_CASE type that \
  describes the relationship (e.g. WORKS_ON, KNOWS), created with MERGE.
- Mention node: label `Mention`, `id` set to EXACTLY the "Mention id" value \
  you are given below — never invent your own. Use MERGE on that `id`, so a \
  retried call re-merges the same Mention rather than creating a duplicate. \
  Link it with `(:Mention)-[:ABOUT]->(:Evidence {id: <the Evidence id you \
  were given>})` and `(:Mention)-[:TOUCHED]->(:Knowledge {...})` to every \
  Knowledge node you created or reused. This is how provenance stays \
  traceable without a direct edge from every fact to its Evidence (see the \
  Mention design).

Process, in order:
1. Read the Evidence text you're given.
2. For each entity worth recording as Knowledge, call \
   `find_canonicalization_candidates` with its name and type BEFORE minting \
   it. If a confident match comes back (near-exact name/alias), reuse that \
   existing node's `id` instead of creating a new one. If the match is \
   ambiguous or there's no match, create a new node — never guess a merge.
3. Use `write_neo4j_cypher` to MERGE the Knowledge nodes/relationships and \
   the Mention node with its ABOUT/TOUCHED edges.
4. If there's nothing worth extracting, do nothing and say so — don't \
   invent Knowledge from thin content.

Reply with a brief plain-text summary of what you extracted (or that there \
was nothing to extract) once you're done issuing writes. Don't call any \
more tools after that.
"""


def build_extraction_prompt(node: EvidenceNode) -> str:
    return (
        f"Evidence id: {node.id}\n"
        f"Mention id: {mention_id_for(node)}\n\n"
        f"Content:\n{node.text or ''}"
    )


def mention_id_for(node: EvidenceNode) -> str:
    """Deterministic, derived from the Evidence id rather than freely chosen
    by the Agent — so a retried extraction re-merges the same Mention
    instead of minting a duplicate (see ingestor.progress: retries must be
    safe to repeat).
    """
    return f"mention:{node.id}"


class ExtractStep:
    """Invokes the Agent to extract Knowledge from every Evidence node's
    content in the tree (the top-level item and every child — an
    attachment's Knowledge should be Mentioned via its own Evidence node, not
    folded into its parent email's), canonicalize against what's already
    known, and write both the Knowledge and its Mention provenance — see
    CONTEXT.md's Agent entry: the Agent performs this write itself, not the
    Pipeline.
    """

    name = "extract"

    async def run(self, node: EvidenceNode, ctx: PipelineContext) -> None:
        if node.text:
            await ctx.agent.run(EXTRACTION_SYSTEM_PROMPT, build_extraction_prompt(node))
        for child in node.children:
            await self.run(child, ctx)
