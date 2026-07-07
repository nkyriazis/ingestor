from __future__ import annotations

import base64

from ingestor.llm import LlamaCppClient

CAPTION_SYSTEM_PROMPT = (
    "You describe images precisely for a knowledge-ingestion pipeline. "
    "Transcribe any visible text verbatim first, then briefly describe "
    "non-text visual content (diagrams, charts, photos). Be concise and "
    "factual — this description is the only way later stages will ever see "
    "this image's content."
)


async def caption_image(llm: LlamaCppClient, image_bytes: bytes, mime_type: str) -> str:
    """Produces a text description of an image (OCR for literal text, vision
    captioning for visual/diagrammatic content) so later Steps only ever
    reason over text, never branching on media type — see CONTEXT.md's
    Conversion entry. A single vision-capable model call does both at once
    (see ADR 0002).
    """
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"
    result = await llm.chat(
        [
            {"role": "system", "content": CAPTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ]
    )
    return result.content
