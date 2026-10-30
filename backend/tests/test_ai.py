from __future__ import annotations

from tests.conftest import make_minimal_pdf_bytes


def _upload_book(client) -> str:
    response = client.post(
        "/api/v1/books",
        files={"file": ("sample.pdf", make_minimal_pdf_bytes(), "application/pdf")},
    )
    return response.json()["id"]


def test_chat_mock_response_is_clearly_labeled(client):
    book_id = _upload_book(client)

    response = client.post(
        "/api/v1/ai/chat",
        json={"book_id": book_id, "question": "Why is this character afraid?", "mode": "research"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["answer_type"] == "mock"
    assert body["provider_status"] == "mock"
    assert body["is_hypothetical"] is False
    assert body["citations"] == []
    assert body["spoiler_scope"]["restricted_to_progress"] is False
    assert "MOCK" in body["answer"]


def test_creative_interaction_is_marked_hypothetical(client):
    book_id = _upload_book(client)

    response = client.post(
        "/api/v1/ai/chat",
        json={
            "book_id": book_id,
            "question": "What if the ending were different?",
            "mode": "creative",
            "interaction_type": "what_if",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_hypothetical"] is True
    assert body["answer_type"] == "hypothetical"


def test_chat_persists_conversation_and_is_retrievable(client):
    book_id = _upload_book(client)

    first = client.post("/api/v1/ai/chat", json={"book_id": book_id, "question": "Who is the protagonist?"})
    conversation_id = first.json()["conversation_id"]

    second = client.post(
        "/api/v1/ai/chat",
        json={"book_id": book_id, "conversation_id": conversation_id, "question": "What do they want?"},
    )
    assert second.json()["conversation_id"] == conversation_id

    conversation = client.get(f"/api/v1/ai/conversations/{conversation_id}")
    assert conversation.status_code == 200
    messages = conversation.json()["messages"]
    # 2 user + 2 assistant messages
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


def test_chat_against_missing_book_is_404(client):
    response = client.post("/api/v1/ai/chat", json={"book_id": "does-not-exist", "question": "Hi"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_missing_conversation_is_404(client):
    response = client.get("/api/v1/ai/conversations/does-not-exist")
    assert response.status_code == 404


def test_chat_rejects_conversation_id_from_a_different_book(client):
    book_a = _upload_book(client)
    book_b = _upload_book(client)

    first = client.post("/api/v1/ai/chat", json={"book_id": book_a, "question": "Who is the protagonist?"})
    conversation_id = first.json()["conversation_id"]

    mismatched = client.post(
        "/api/v1/ai/chat",
        json={"book_id": book_b, "conversation_id": conversation_id, "question": "Different book entirely"},
    )
    assert mismatched.status_code == 404
    assert mismatched.json()["error"]["code"] == "NOT_FOUND"
