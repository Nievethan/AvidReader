"""Character portrait generation.

`CloudflarePortraitGenerator` calls a Cloudflare-hosted text-to-image model
(flux-1-schnell by default -- free Workers AI allowance). The offline
`NotAvailablePortraitGenerator` is used without credentials: no image is
made and the UI keeps showing the role icon.

`build_portrait_prompt` builds the prompt ONLY from the appearance the
extractor found in the text read so far, and scrubs every character name and
the book title out of it. That keeps portraits spoiler-free and stops the
model from reproducing a film actor's face for a famous character.

Only real proper names are scrubbed: a "character" the extractor called
"The man" must not strip the word "man" out of every other prompt (that is
how "a small grey man" became a grey dog and "a bony woman" a skeleton).
Non-answers such as "not described directly" never reach the prompt, and
`build_portrait_prompt(..., safe=True)` is the softened retry used when
Cloudflare's safety filter wrongly flags a prompt as NSFW.
"""
from __future__ import annotations

import re
from typing import Protocol

from app.integrations.cloudflare import CloudflareClient, CloudflareError

_FALLBACK_SUBJECT = "an ordinary adult person"
_PROMPT_TEMPLATE = (
    "Photorealistic portrait photograph of {subject}. Head and shoulders, looking at the camera, "
    "soft natural window light, shallow depth of field, 85mm lens, plain muted background, "
    "detailed skin texture, realistic. Not a celebrity. No text, no watermark."
)
# Softened retry for Cloudflare's NSFW false positives: says the subject is
# dressed and drops body/skin wording that pushes the filter's score up.
_SAFE_PROMPT_TEMPLATE = (
    "Photorealistic portrait photograph of {subject}, fully clothed in period costume. "
    "Head and shoulders, looking at the camera, soft natural light, plain muted background, "
    "realistic. Not a celebrity. No text, no watermark."
)
# Words dropped from the subject on the softened retry.
_SAFE_DROP_WORDS = re.compile(
    r"\b(beautiful|gorgeous|pretty|attractive|sexy|seductive|alluring|voluptuous|curvy|"
    r"naked|nude|bare|shirtless|topless|skin|sensual|lovely|stunning)\b,?\s*",
    re.IGNORECASE,
)

# Words in a character's "name" that are titles, honorifics or plain
# English: never scrubbed from prompts, since they identify nobody and
# removing them mangles the description ("Old Nan" must not delete "old",
# "Ser Boros" must not delete "ser"). Lower-case name words are skipped too.
_KEEP_WORDS = frozenset(
    {
        "mr", "mrs", "ms", "miss", "dr", "sir", "ser", "lady", "lord", "the", "of", "and", "von", "van", "de",
        "a", "an", "old", "young", "little", "big", "great", "elder", "younger",
        "king", "queen", "prince", "princess", "duke", "duchess", "earl", "count", "countess", "baron",
        "knight", "maester", "septa", "septon", "magister", "khal", "khaleesi", "captain", "commander",
        "father", "mother", "brother", "sister", "uncle", "aunt", "grandmother", "grandfather",
        "man", "woman", "men", "women", "boy", "girl", "child", "baby", "lad", "lass",
        "guard", "soldier", "servant", "killer", "stranger", "rider", "priest", "nurse", "cook",
    }
)
# A "character" whose name starts with one of these is a description, not a
# name ("The man", "A guard"): it is never used as a source of words to scrub.
_GENERIC_NAME_START = re.compile(r"^\s*(the|a|an|some|another|one)\s", re.IGNORECASE)

# The extractor sometimes writes a non-answer instead of "" -- those must
# never be painted ("Photorealistic portrait photograph of not described directly").
_NON_ANSWER = re.compile(
    r"^\s*(?:n/?a|none|null|nil|unknown|unspecified|-+|\.+|"
    r"(?:no|not)\s+(?:physical\s+|visual\s+)?(?:description|details?|info(?:rmation)?)(?:\s+(?:given|provided|available))?|"
    r"(?:appearance\s+)?(?:is\s+)?not\s+(?:directly\s+|explicitly\s+|physically\s+|clearly\s+)?"
    r"(?:described|mentioned|specified|stated|given|provided|known|detailed)\b.*)"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)


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


def is_nsfw_rejection(exc: BaseException) -> bool:
    """Cloudflare's prompt safety filter: HTTP 400 "Input prompt contains NSFW content"."""
    return isinstance(exc, CloudflareError) and "nsfw" in str(exc).casefold()


def meaningful_appearance(value: str | None) -> str | None:
    """The appearance text, or None if it's empty or a non-answer such as
    "not described directly", "unknown" or "N/A"."""
    text = (value or "").strip()
    if not text or _NON_ANSWER.match(text):
        return None
    return text


def _scrub_terms(names: list[str], book_title: str | None) -> list[str]:
    """Proper-name words to remove: capitalized, 3+ letters, not a title or
    common word, and not from a generic "character" such as "The man"."""
    terms: set[str] = set()
    sources = [n for n in names if n and not _GENERIC_NAME_START.match(n)]
    for value in [*sources, book_title or ""]:
        for word in re.findall(r"[A-Za-z][A-Za-z'\-]+", value):
            if len(word) >= 3 and word[0].isupper() and word.casefold() not in _KEEP_WORDS:
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


def build_portrait_prompt(
    appearance: str | None, *, names: list[str], book_title: str | None = None, safe: bool = False
) -> str:
    """`safe=True` is the softened retry after an NSFW false positive."""
    subject = scrub_names(meaningful_appearance(appearance) or "", names, book_title)
    if safe:
        subject = re.sub(r"\s{2,}", " ", _SAFE_DROP_WORDS.sub("", subject)).strip(" ,;:")
    if len(subject) < 3:
        subject = _FALLBACK_SUBJECT
    template = _SAFE_PROMPT_TEMPLATE if safe else _PROMPT_TEMPLATE
    return template.format(subject=subject.rstrip("."))
