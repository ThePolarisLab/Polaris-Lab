def test_health(client): assert client.get("/health").json()=={"status":"ok"}
def test_knowledge_relationship_and_briefing(client):
    first=client.post("/api/v1/knowledge",json={"title":"Every Builder matters","content":"Recognition is not the measure of a Builder. Contribution is.","knowledge_type":"foundation_principle","author":"founder","importance":5,"confidence":1.0,"truth_status":"verified","source":"foundation","visibility":"organization"})
    assert first.status_code==201
    second=client.post("/api/v1/knowledge",json={"title":"Foundation dedication","content":"Dedicated to every Builder whose wisdom deserved to outlive them.","knowledge_type":"foundation_principle","author":"founder","importance":5,"confidence":1.0,"truth_status":"verified","source":"foundation","visibility":"organization"})
    assert second.status_code==201
    relation=client.post("/api/v1/knowledge/relationships",json={"source_knowledge_id":first.json()["id"],"target_knowledge_id":second.json()["id"],"relationship_type":"reinforces","evidence":"Both define the Builder-centered purpose of Polaris.","confidence":1.0})
    assert relation.status_code==201
    found=client.get("/api/v1/knowledge",params={"query":"Builder"})
    assert found.status_code==200 and len(found.json())==2
    briefing=client.get("/api/v1/briefing/today").json()
    assert briefing["knowledge_count"]==2 and len(briefing["featured_knowledge"])==2
