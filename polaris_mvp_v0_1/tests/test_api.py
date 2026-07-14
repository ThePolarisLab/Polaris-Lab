def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_memory_decision_timeline_and_briefing(client):
    memory_response = client.post(
        "/api/v1/memories",
        json={
            "title": "Review supplier payments",
            "content": "Review payment schedule before approving transfers.",
            "memory_type": "operational",
            "source": "builder",
            "importance": 5,
            "occurred_at": "2026-07-13T09:00:00",
        },
    )
    assert memory_response.status_code == 201
    assert memory_response.json()["importance"] == 5

    decision_response = client.post(
        "/api/v1/decisions",
        json={
            "title": "Adopt modular monolith",
            "decision": "Build Polaris v0.1 as a modular monolith.",
            "rationale": "It minimizes operational complexity while preserving boundaries.",
            "status": "approved",
            "decided_at": "2026-07-13T10:00:00",
        },
    )
    assert decision_response.status_code == 201

    timeline = client.get("/api/v1/timeline")
    assert timeline.status_code == 200
    assert len(timeline.json()) == 2
    assert timeline.json()[0]["item_type"] == "decision"

    briefing = client.get("/api/v1/briefing/today")
    assert briefing.status_code == 200
    payload = briefing.json()
    assert payload["memory_count"] == 1
    assert payload["decision_count"] == 1
    assert payload["priorities"][0]["title"] == "Review supplier payments"
