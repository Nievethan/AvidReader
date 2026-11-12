"""Shared async Cloudflare Workers AI client.

Gitae's prototype script calls the REST API with blocking `httpx.post`,
which would freeze the FastAPI event loop. This module is the async home for
both embedding (`embed`) and chat generation (`generate`); Gitae's feature
prompts reuse `generate`.

REST shape (settled by the prototype):
  POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}
  Authorization: Bearer {API_TOKEN}
  -> {"success": bool, "result": {...}, "errors": [...]}

Embedding models take {"text": [...]} and return result.data = [[...], ...].
Chat models take {"messages": [...], "max_tokens": n} and return either
result.response (classic models) or result.choices[0].message.content
(OpenAI-compatible models).
[Verify against current Cloudflare docs: request/response shape, batch limit
(100 texts for bge models), max input tokens.]
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
# Reasoning models may emit their hidden reasoning; it is never shown to users.
_THINK_BLOCK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL | re.IGNORECASE)


class CloudflareError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class CloudflareNotConfiguredError(CloudflareError):
    pass


class CloudflareClient:
    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not account_id or not api_token:
            raise CloudflareNotConfiguredError("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must be set.")
        self._account_id = account_id
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(
        self,
        model: str,
        payload: dict,
        *,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> dict:
        """POST to /ai/run/{model}; returns the `result` object. Retries
        429/5xx/timeouts with exponential backoff (honouring Retry-After).
        `timeout` / `max_retries` override the client defaults for one call
        (the interactive Q&A path uses a short timeout and few retries)."""
        url = f"/accounts/{self._account_id}/ai/run/{model}"
        retries = self._max_retries if max_retries is None else max_retries
        request_kwargs = {"timeout": timeout} if timeout is not None else {}
        attempt = 0
        while True:
            try:
                response = await self._http.post(url, json=payload, **request_kwargs)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                error = CloudflareError(f"Cloudflare request failed: {type(exc).__name__}", retryable=True)
                retry_after = None
            else:
                if response.status_code < 400:
                    return self._parse_result(response)
                retry_after = _retry_after_seconds(response)
                error = CloudflareError(
                    _error_message(response),
                    status_code=response.status_code,
                    retryable=response.status_code in _RETRYABLE_STATUS,
                )
            if not error.retryable or attempt >= retries:
                raise error
            delay = retry_after if retry_after is not None else self._backoff_base * (2**attempt)
            logger.warning("Cloudflare call failed (%s); retry %d in %.1fs", error, attempt + 1, delay)
            await self._sleep(delay)
            attempt += 1

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        result = await self.run(model, {"text": texts})
        data = result.get("data")
        if not isinstance(data, list):
            raise CloudflareError("Unexpected embedding response: missing result.data")
        return data

    async def generate(
        self,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float = 0.2,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> str:
        """Chat completion; returns the reply text with any <think> block removed."""
        result = await self.run(
            model,
            {"messages": messages, "max_tokens": max_tokens, "temperature": temperature},
            timeout=timeout,
            max_retries=max_retries,
        )
        response_field = result.get("response")
        text = response_field if isinstance(response_field, str) else None
        if not text:
            try:
                content = result["choices"][0]["message"]["content"]
                text = content if isinstance(content, str) else None
            except (KeyError, IndexError, TypeError):
                pass
        if not text and isinstance(response_field, (dict, list)):
            # A JSON-mode request (e.g. "return one JSON object") can make
            # some models put the already-parsed object directly in
            # `response` instead of a string -- serialize it back to text
            # rather than treating "present but not a string" as "missing".
            text = json.dumps(response_field)
        if not isinstance(text, str) or not text.strip():
            raise CloudflareError(
                "Chat model returned no answer text (a reasoning model may have spent max_tokens on reasoning)."
            )
        return _THINK_BLOCK.sub("", text).strip()

    @staticmethod
    def _parse_result(response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError as exc:
            raise CloudflareError("Cloudflare returned a non-JSON response.") from exc
        if not body.get("success", True):
            raise CloudflareError(_error_message(response), status_code=response.status_code)
        result = body.get("result")
        if not isinstance(result, dict):
            raise CloudflareError("Cloudflare response had no result object.")
        return result


def _retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    try:
        return min(float(raw), 30.0) if raw else None
    except ValueError:
        return None


def _error_message(response: httpx.Response) -> str:
    try:
        errors = response.json().get("errors") or []
        detail = "; ".join(str(e.get("message", e)) for e in errors)
    except (ValueError, AttributeError):
        detail = ""
    return f"Cloudflare API error {response.status_code}" + (f": {detail}" if detail else "")
