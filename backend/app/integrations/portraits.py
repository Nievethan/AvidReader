"""Character portrait generation.

`CloudflarePortraitGenerator` calls a Cloudflare-hosted text-to-image model
(flux-1-schnell by default -- free Workers AI allowance). The offline
`NotAvailablePortraitGenerator` is used without credentials: no image is
made and the UI keeps showing the role icon.

`build_portrait_prompt` builds the prompt ONLY from the appearance the
extractor found in the text read so far, and scrubs every character name and
the book title out of it. That keeps portraits spoiler-free and stops the
model from reproducing a film actor's face for a famous character.
"""
from __future__ import annotations

import re
from typing import Protocol

from app.integrations.cloudflare import CloudflareClient

_FALLBACK_SUBJECT = "an ordinary adult person"
_PROMPT_TEMPLATE = (
    "Photorealistic portrait photograph of {subject}. Head and shoulders, looking at the camera, "
    "soft natural window light, shallow depth of field, 85mm lens, plain muted background, "
    "detailed skin texture, realistic. Not a celebrity. No text, no watermark."
)
# Name words this short (or these honorifics) are kept: scrubbing "Mr" or
# "the" would mangle the description without hiding anyone's identity.
_KEEP_WORDS = frozenset({"mr", "mrs", "ms", "miss", "dr", "sir", "lady", "lord", "the", "of", "and", "von", "van", "de"})


class PortraitGenerator(Protocol):
    available: bool

    async def generate(self, prompt: str) -> bytes: ...


class NotAvailablePortraitGenerator:
    available = False

    async def generate(self, prompt: str) -> bytes:  # pragma: no cover - never called
        raise RuntimeError("No image model configured.")


class CloudflarePortraitGenerator:
    available = True

    def __init__(self, client: CloudflareClient, model: str, *, steps: int, timeout: float) -> None:
        self._client = client
        self.model = model
        self._steps = steps
        self._timeout = timeout

    async def generate(self, prompt: str) -> bytes:
        return await self._client.generate_image(
            self.model, prompt, steps=self._steps, timeout=self._timeout, max_retries=2
        )


def _scrub_terms(names: list[str], book_title: str | None) -> list[str]:
    terms: set[str] = set()
    for value in [*names, book_title or ""]:
        for word in re.findall(r"[A-Za-z][A-Za-z'\-]+", value):
            if len(word) >= 3 and word.casefold() not in _KEEP_WORDS:
                terms.add(word)
    return sorted(terms, key=len, reverse=True)


def scrub_names(text: str, names: list[str], book_title: str | None = None) -> str:
    """Removes every name word (and possessive/plural forms like "Potters",
    "Harry's") of every character, plus the book title's words."""
    for term in _scrub_terms(names, book_title):
        text = re.sub(r"(?<![\w])" + re.escape(term) + r"(?:'s|s)?(?![\w])", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"([,;:])\s*(?=[,;:.]|$)", "", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;:")


def build_portrait_prompt(appearance: str | None, *, names: list[str], book_title: str | None = None) -> str:
    subject = scrub_names(appearance or "", names, book_title)
    if len(subject) < 3:
        subject = _FALLBACK_SUBJECT
    return _PROMPT_TEMPLATE.format(subject=subject.rstrip("."))
