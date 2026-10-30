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

    optional = body["optional_dependencies"]
    assert optional["qdrant"]["configured"] is False
    assert optional["qdrant"]["status"] == "not_checked"
    assert optional["neo4j"]["configured"] is False
    assert optional["neo4j"]["status"] == "not_checked"
