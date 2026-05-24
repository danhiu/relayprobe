import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_detect_dry_run_authentic(client):
    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "claude-opus-4-7",
            "rounds": 11,
            "budget_usd": 0.5,
            "dry_run": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score"] >= 90
    assert body["verdict"] == "authentic"
    assert "claude-opus-4-7" in body["summary_zh"] or "Claude" in body["summary_zh"]
    assert "online" in body["dimensions"]


def test_detect_unknown_model_returns_400(client):
    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "no-such-model",
            "dry_run": True,
        },
    )
    assert r.status_code == 400
    assert "unknown model" in r.json()["detail"].lower()


def test_detect_validation_rounds_too_high_returns_422(client):
    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "claude-opus-4-7",
            "rounds": 9999,
        },
    )
    assert r.status_code == 422


def test_detect_does_not_leak_api_key(client, caplog):
    import logging

    caplog.set_level(logging.INFO)
    client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-VERYSECRETKEY12345",
            "model": "claude-opus-4-7",
            "dry_run": True,
        },
    )
    full = "\n".join(rec.getMessage() for rec in caplog.records)
    assert "sk-VERYSECRETKEY12345" not in full


def test_async_submit_then_poll_to_completion(client):
    import time

    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "claude-opus-4-7",
            "rounds": 11,
            "budget_usd": 0.5,
            "dry_run": True,
            "mode": "async",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    task_id = body["task_id"]
    assert task_id.startswith("rp-")

    # Poll. dry_run is fast — should land within a couple of ticks.
    deadline = time.time() + 10
    final = None
    while time.time() < deadline:
        g = client.get(f"/detect/{task_id}")
        assert g.status_code == 200
        if g.json()["status"] == "completed":
            final = g.json()
            break
        time.sleep(0.05)
    assert final is not None, "async job did not finish in 10s"
    assert final["verdict"] == "authentic"
    assert final["score"] >= 90


def test_async_unknown_model_fails(client):
    import time

    r = client.post(
        "/detect",
        json={
            "base_url": "https://x",
            "api_key": "sk-test",
            "model": "no-such-model",
            "dry_run": True,
            "mode": "async",
        },
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]

    deadline = time.time() + 5
    final = None
    while time.time() < deadline:
        g = client.get(f"/detect/{task_id}").json()
        if g["status"] == "failed":
            final = g
            break
        time.sleep(0.05)
    assert final is not None
    assert final["status"] == "failed"


def test_get_unknown_task_id_returns_404(client):
    r = client.get("/detect/rp-nope")
    assert r.status_code == 404
