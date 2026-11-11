import asyncio
import json

import httpx
import pytest

from app.integrations.cloudflare import (
    CloudflareClient,
    CloudflareError,
    CloudflareNotConfiguredError,
    _error_message,
    _retry_after_seconds,
)

MODEL = "@cf/baai/bge-base-en-v1.5"


def make_client(handler, *, max_retries=3, sleeps=None):
    sleeps = sleeps if sleeps is not None else []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    return CloudflareClient(
        "acct", "tok",
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep, backoff_base=0.5, max_retries=max_retries,
    ), sleeps


def ok(result):
    return httpx.Response(200, json={"success": True, "result": result})


def test_requires_credentials():
    with pytest.raises(CloudflareNotConfiguredError):
        CloudflareClient("", "tok")
    with pytest.raises(CloudflareNotConfiguredError):
        CloudflareClient("acct", "")
    assert issubclass(CloudflareNotConfiguredError, CloudflareError)


def test_run_sends_auth_and_payload_and_returns_result():
    seen = {}

    def handler(request):
        seen["url"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return ok({"answer": 42})

    client, _ = make_client(handler)
    result = asyncio.run(client.run(MODEL, {"text": ["hi"]}))
    assert result == {"answer": 42}
    assert seen["url"] == f"/client/v4/accounts/acct/ai/run/{MODEL}"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"] == {"text": ["hi"]}


def test_embed_returns_vectors():
    client, _ = make_client(lambda r: ok({"shape": [1, 2], "data": [[0.1, 0.2]]}))
    assert asyncio.run(client.embed(MODEL, ["hi"])) == [[0.1, 0.2]]


def test_embed_without_data_is_an_error():
    client, _ = make_client(lambda r: ok({"shape": [0, 0]}))
    with pytest.raises(CloudflareError, match="missing result.data"):
        asyncio.run(client.embed(MODEL, ["hi"]))


def test_retries_429_then_5xx_with_backoff_and_retry_after():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={"success": False, "errors": []})
        if len(calls) == 2:
            return httpx.Response(503, json={})
        return ok({"data": [[1.0]]})

    client, sleeps = make_client(handler)
    assert asyncio.run(client.embed(MODEL, ["x"])) == [[1.0]]
    assert len(calls) == 3
    assert sleeps == [2.0, 1.0]  # Retry-After honoured, then 0.5 * 2**1


@pytest.mark.parametrize("exc", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")])
def test_retries_transport_errors_and_timeouts(exc):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise exc
        return ok({"data": [[1.0]]})

    client, sleeps = make_client(handler)
    assert asyncio.run(client.embed(MODEL, ["x"])) == [[1.0]]
    assert sleeps == [0.5]


def test_gives_up_after_max_retries():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500, json={"errors": [{"message": "server on fire"}]})

    client, sleeps = make_client(handler, max_retries=2)
    with pytest.raises(CloudflareError, match="500: server on fire") as info:
        asyncio.run(client.run(MODEL, {}))
    assert len(calls) == 3 and len(sleeps) == 2
    assert info.value.status_code == 500 and info.value.retryable is True


def test_transport_error_is_raised_after_retries():
    def handler(request):
        raise httpx.ConnectError("down")

    client, _ = make_client(handler, max_retries=1)
    with pytest.raises(CloudflareError, match="ConnectError") as info:
        asyncio.run(client.run(MODEL, {}))
    assert info.value.status_code is None


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"success": False, "errors": [{"message": "bad token"}]})

    client, sleeps = make_client(handler)
    with pytest.raises(CloudflareError, match="401: bad token") as info:
        asyncio.run(client.run(MODEL, {}))
    assert len(calls) == 1 and sleeps == []
    assert info.value.retryable is False


def test_non_json_success_response():
    client, _ = make_client(lambda r: httpx.Response(200, text="<html>oops</html>"))
    with pytest.raises(CloudflareError, match="non-JSON"):
        asyncio.run(client.run(MODEL, {}))


def test_success_false_in_body_is_an_error():
    client, _ = make_client(
        lambda r: httpx.Response(200, json={"success": False, "errors": [{"message": "model gone"}]})
    )
    with pytest.raises(CloudflareError, match="model gone"):
        asyncio.run(client.run(MODEL, {}))


def test_missing_result_object_is_an_error():
    client, _ = make_client(lambda r: httpx.Response(200, json={"success": True, "result": "nope"}))
    with pytest.raises(CloudflareError, match="no result object"):
        asyncio.run(client.run(MODEL, {}))


def test_aclose():
    client, _ = make_client(lambda r: ok({}))
    asyncio.run(client.aclose())


def test_retry_after_parsing():
    def resp(value):
        return httpx.Response(429, headers={"Retry-After": value} if value is not None else {})

    assert _retry_after_seconds(resp("3")) == 3.0
    assert _retry_after_seconds(resp("999")) == 30.0  # capped
    assert _retry_after_seconds(resp("tomorrow")) is None
    assert _retry_after_seconds(resp(None)) is None


def test_error_message_shapes():
    assert _error_message(httpx.Response(500, json={"errors": [{"message": "a"}, {"message": "b"}]})) == (
        "Cloudflare API error 500: a; b"
    )
    assert _error_message(httpx.Response(502, text="not json")) == "Cloudflare API error 502"
    assert _error_message(httpx.Response(502, json=["unexpected"])) == "Cloudflare API error 502"
    assert _error_message(httpx.Response(500, json={"errors": []})) == "Cloudflare API error 500"
