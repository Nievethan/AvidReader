"""Chat-model seam for grounded answers.

`CloudflareChatModel` calls Workers AI through the shared async client.
`OfflineChatModel` needs no network or credentials: it answers extractively
by quoting the best-matching excerpt sentences with a citation. It exists so
the app and tests work offline, and its answers are labelled as offline.
"""
from __future__ import annotations

import logging
import re
from typing import Protocol

from app.core.config import Settings
from app.integrations.cloudflare import CloudflareClient

logger = logging.getLogger(__name__)

OFFLINE_PREFIX = "[Offline answer, no AI model configured]"
_EXCERPT = re.compile(r"^\[S(\d+)\][^\n]*\n(.*?)(?=^\[S\d+\]|\Z)", re.DOTALL | re.MULTILINE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9']+")
_STOPWORDS = frozenset(
    "a an and are as at be but by did do does for from had has have he her his how i in is it its of on or "
    "she so that the their them they this to was were what when where which who why will with you".split()
)


class ChatModel(Protocol):
    name: str
    status: str  # provider_status reported for answers from this model

    async def complete(self, messages: list[dict], *, max_tokens: int) -> str: ...


class CloudflareChatModel:
    status = "ok"

    def __init__(self, client: CloudflareClient, model: str, *, timeout: float, max_retries: int = 1) -> None:
        self._client = client
        self.name = model
        self._timeout = timeout
        self._max_retries = max_retries

    async def complete(self, messages: list[dict], *, max_tokens: int) -> str:
        if "qwen3" in self.name:
            # Qwen3 thinks by default; "/no_think" skips it (as in Gitae's script) to save time and tokens.
            messages = [*messages[:-1], {**messages[-1], "content": "/no_think\n" + messages[-1]["content"]}]
        return await self._client.generate(
            self.name,
            messages,
            max_tokens=max_tokens,
            timeout=self._timeout,
            max_retries=self._max_retries,
        )


class OfflineChatModel:
    """Picks the excerpt sentences sharing the most content words with the
    question and returns them with their [S#] marker. For story_continues it
    explains that a real model is needed."""

    name = "offline-extractive"
    status = "fake"

    async def complete(self, messages: list[dict], *, max_tokens: int) -> str:
        prompt = messages[-1]["content"]
        if "Continue the story" in messages[0]["content"]:
            return f"{OFFLINE_PREFIX} Story continuations need a configured AI model. [S1]"
        question = prompt.rsplit("Question:", 1)[-1]
        wanted = _content_words(question)
        best: tuple[int, str, str] | None = None
        for marker, body in _EXCERPT.findall(prompt):
            for sentence in _SENTENCE.split(" ".join(body.split())):
                score = len(wanted & _content_words(sentence))
                if score and (best is None or score > best[0]):
                    best = (score, sentence, marker)
        if best is None:
            return "NOT_FOUND"
        return f'{OFFLINE_PREFIX} The book says: "{best[1]}" [S{best[2]}]'


def _content_words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOPWORDS and len(word) > 2}


def build_chat_model(settings: Settings, client: CloudflareClient | None = None) -> ChatModel:
    backend = settings.answer_backend
    has_credentials = bool(settings.cloudflare_account_id and settings.cloudflare_api_token)
    if backend == "fake" or (backend == "auto" and not has_credentials):
        if backend == "auto":
            logger.warning("Cloudflare credentials not set; chat answers use the OFFLINE extractive fallback.")
        return OfflineChatModel()
    if backend not in ("auto", "cloudflare"):
        raise ValueError(f"Unknown ANSWER_BACKEND: {backend!r}")
    client = client or CloudflareClient(settings.cloudflare_account_id, settings.cloudflare_api_token)
    return CloudflareChatModel(client, settings.cloudflare_text_model, timeout=settings.answer_timeout_seconds)
