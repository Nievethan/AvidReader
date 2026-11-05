"""Shared async Cloudflare Workers AI client.

Gitae's prototype script calls the REST API with blocking `httpx.post`,
which would freeze the FastAPI event loop. This module is the async home for
both embedding (written here, Umer) and chat generation (Gitae adds
`generate` on top of `run`).

REST shape (settled by the prototype):
  POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODEL}
  Authorization: Bearer {API_TOKEN}
  -> {"success": bool, "result": {...}, "errors": [...]}

Embedding models take {"text": [...]} and return result.data = [[...], ...].
[Verify against current Cloudflare docs: request/response shape, batch limit
(100 texts for bge models), max input tokens.]
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


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

    async def run(self, model: str, payload: dict) -> dict:
        """POST to /ai/run/{model}; returns the `result` object. Retries
        429/5xx/timeouts with exponential backoff (honouring Retry-After)."""
        url = f"/accounts/{self._account_id}/ai/run/{model}"
        attempt = 0
        while True:
            try:
                response = await self._http.post(url, json=payload)
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
            if not error.retryable or attempt >= self._max_retries:
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
