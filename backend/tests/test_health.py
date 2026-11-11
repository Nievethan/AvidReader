from __future__ import annotations


def test_health_is_truthful_about_process_only(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_database_and_optional_dependencies(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ready"
    assert body["database"]["status"] == "ok"

    # Step 6: Qdrant is checked for real (in-memory embedded mode in tests).
    assert body["vector_store"] == {"configured": True, "mode": "memory", "status": "ok"}

    optional = body["optional_dependencies"]
    assert "qdrant" not in optional
    assert optional["neo4j"]["configured"] is False
    assert optional["neo4j"]["status"] == "not_checked"
