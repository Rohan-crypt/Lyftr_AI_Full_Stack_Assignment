import os
import pytest
from fastapi.testclient import TestClient

# Configure environment before importing app
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["LLM_API_KEYS"] = "mock_key_1,mock_key_2"
os.environ["DATABASE_URL"] = "sqlite:///./data/test_app.db"

from app.main import app
from app.database import init_db
from app.config import DB_FILE_PATH

@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(DB_FILE_PATH):
        try:
            os.remove(DB_FILE_PATH)
        except Exception:
            pass
    init_db()
    yield

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] == 2
    assert data["cache_enabled"] is True

def test_chat_live_inference_and_caching(client):
    session_id = "test-session-1"
    payload = {
        "session_id": session_id,
        "message": "What is the capital of France?"
    }
    
    # 1. First call -> LIVE_INFERENCE
    res1 = client.post("/chat", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["session_id"] == session_id
    assert len(data1["reply"]) > 0
    assert data1["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert data1["metadata"]["key_id"] == "key_1"
    assert data1["metadata"]["fallback_attempts"] == 0
    assert isinstance(data1["metadata"]["latency_ms"], int)
    assert data1["metadata"]["input_tokens"] > 0
    assert data1["metadata"]["output_tokens"] > 0

    # 2. Same first message in a NEW session -> LLM_CACHE
    new_session_id = "test-session-2"
    res2 = client.post("/chat", json={
        "session_id": new_session_id,
        "message": "What is the capital of France?"
    })
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["session_id"] == new_session_id
    assert data2["reply"] == data1["reply"]
    assert data2["metadata"]["resolution_source"] == "LLM_CACHE"
    assert data2["metadata"]["key_id"] is None
    assert data2["metadata"]["fallback_attempts"] == 0
    assert data2["metadata"]["input_tokens"] == data1["metadata"]["input_tokens"]
    assert data2["metadata"]["output_tokens"] == data1["metadata"]["output_tokens"]
    assert data2["metadata"]["latency_ms"] <= data1["metadata"]["latency_ms"]

def test_chat_validation_errors(client):
    # Empty message
    res = client.post("/chat", json={"session_id": "s1", "message": "   "})
    assert res.status_code == 422
    assert "detail" in res.json()

    # Message over 4000 characters
    long_msg = "a" * 4001
    res = client.post("/chat", json={"session_id": "s1", "message": long_msg})
    assert res.status_code == 422
    assert "detail" in res.json()

    # Missing session_id
    res = client.post("/chat", json={"message": "hello"})
    assert res.status_code == 422
    assert "detail" in res.json()

    # Malformed JSON
    res = client.post("/chat", content="invalid json", headers={"Content-Type": "application/json"})
    assert res.status_code == 422
    assert "detail" in res.json()

def test_failover_simulation(client):
    # key_1 fails with 429 -> fails over to key_2
    res = client.post(
        "/chat",
        json={"session_id": "sim-s1", "message": "Simulate failover test 1"},
        headers={"X-Simulate-Failure": "key_1=429"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1
    assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

    # key_1 fails with 500 -> fails over to key_2
    res = client.post(
        "/chat",
        json={"session_id": "sim-s2", "message": "Simulate failover test 2"},
        headers={"X-Simulate-Failure": "key_1=500"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["key_id"] == "key_2"
    assert data["metadata"]["fallback_attempts"] == 1

    # All keys fail with *=429 -> 503 "all providers unavailable"
    res = client.post(
        "/chat",
        json={"session_id": "sim-s3", "message": "Simulate all keys fail"},
        headers={"X-Simulate-Failure": "*=429"}
    )
    assert res.status_code == 503
    assert res.json() == {"detail": "all providers unavailable"}

    # Verify nothing was added to history for failed request
    hist_res = client.get("/sessions/sim-s3/messages")
    assert hist_res.status_code == 404
    assert hist_res.json() == {"detail": "session not found"}

def test_session_history_endpoint(client):
    session_id = "history-session"
    
    # Send message 1
    client.post("/chat", json={"session_id": session_id, "message": "Hello AI"})
    # Send message 2
    client.post("/chat", json={"session_id": session_id, "message": "What is 2+2?"})

    # Retrieve history
    res = client.get(f"/sessions/{session_id}/messages")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    messages = data["messages"]
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello AI"
    assert messages[1]["role"] == "assistant"
    assert "metadata" in messages[1]
    assert messages[1]["metadata"]["resolution_source"] in ("LIVE_INFERENCE", "LLM_CACHE")
    assert "input_tokens" in messages[1]["metadata"]
    assert "output_tokens" in messages[1]["metadata"]

    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "What is 2+2?"
    assert messages[3]["role"] == "assistant"

def test_multi_turn_context(client):
    session_id = "multi-turn-session"
    res1 = client.post("/chat", json={"session_id": session_id, "message": "My name is Alice."})
    tokens1 = res1.json()["metadata"]["input_tokens"]

    # 2nd turn has history, so prompt tokens should be higher than 1st turn
    res2 = client.post("/chat", json={"session_id": session_id, "message": "What is my name?"})
    tokens2 = res2.json()["metadata"]["input_tokens"]
    assert tokens2 > tokens1

def test_token_tracking_per_request(client):
    # Two equal-length first messages in two new sessions report about the same input_tokens
    s1 = "s-equal-1"
    s2 = "s-equal-2"
    msg1 = "Tell me a short joke."
    msg2 = "Tell me a short poem."
    res1 = client.post("/chat", json={"session_id": s1, "message": msg1})
    res2 = client.post("/chat", json={"session_id": s2, "message": msg2})
    assert abs(res1.json()["metadata"]["input_tokens"] - res2.json()["metadata"]["input_tokens"]) <= 2

def test_unknown_session_returns_404(client):
    res = client.get("/sessions/non-existent-session-xyz/messages")
    assert res.status_code == 404
    assert res.json() == {"detail": "session not found"}
