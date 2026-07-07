from __future__ import annotations

import io
import os

import pytest
from PIL import Image, ImageDraw

from ingestor.captioning import caption_image
from ingestor.llm import LlamaCppClient

pytestmark = [pytest.mark.seam2, pytest.mark.asyncio]

LLAMACPP_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "Qwen3.6-27B-Q4_K_M.gguf")


def _slide_image_bytes(text: str) -> bytes:
    image = Image.new("RGB", (400, 200), color="white")
    ImageDraw.Draw(image).text((20, 80), text, fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def test_captions_visible_text_in_a_slide_image() -> None:
    llm = LlamaCppClient(base_url=LLAMACPP_BASE_URL, model=LLAMACPP_MODEL)

    caption = await caption_image(
        llm, _slide_image_bytes("Q3 Roadmap: Ship v2 by August"), "image/png"
    )

    assert "august" in caption.lower()
    assert "v2" in caption.lower() or "roadmap" in caption.lower()
