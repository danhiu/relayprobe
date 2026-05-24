"""Tests for app.jobs.JobStore and reaper."""
from __future__ import annotations

import asyncio

import pytest

from app.detector.types import DetectRequest, DetectResponse
from app.jobs import JobStore


def _req() -> DetectRequest:
    return DetectRequest(
        base_url="https://x",
        api_key="sk-test",
        model="claude-opus-4-7",
        dry_run=True,
    )


def _ok(req: DetectRequest) -> DetectResponse:
    return DetectResponse(
        task_id=req.task_id or "rp-fixed",
        status="completed",
        score=99,
        verdict="authentic",
        summary_zh="ok",
        summary_en="ok",
        dimensions={},
        capability_flags={},
    )


@pytest.mark.asyncio
async def test_submit_then_complete():
    store = JobStore()

    async def runner(req):
        await asyncio.sleep(0)
        return _ok(req)

    rec = store.submit(_req(), runner)
    assert rec.status == "running"
    assert rec.task_id.startswith("rp-")

    await rec.task
    got = store.get(rec.task_id)
    assert got is not None
    assert got.status == "completed"
    assert got.result is not None
    assert got.result.score == 99


@pytest.mark.asyncio
async def test_submit_failure_captured():
    store = JobStore()

    async def runner(req):
        raise RuntimeError("boom")

    rec = store.submit(_req(), runner)
    await rec.task
    got = store.get(rec.task_id)
    assert got.status == "failed"
    assert "boom" in (got.error or "")


@pytest.mark.asyncio
async def test_duplicate_task_id_rejected():
    store = JobStore()

    async def runner(req):
        await asyncio.sleep(0)
        return _ok(req)

    req = _req()
    req.task_id = "rp-fixed"
    store.submit(req, runner)
    with pytest.raises(ValueError):
        store.submit(req, runner)


@pytest.mark.asyncio
async def test_reap_drops_old_completed_jobs():
    store = JobStore()

    async def runner(req):
        return _ok(req)

    rec = store.submit(_req(), runner)
    await rec.task
    assert store.get(rec.task_id) is not None

    # Pretend a long time has passed.
    rec_internal = store.get(rec.task_id)
    rec_internal.finished_at = 0.0
    dropped = store.reap(now=10_000_000.0)
    assert dropped == 1
    assert store.get(rec.task_id) is None


@pytest.mark.asyncio
async def test_reap_keeps_running_jobs():
    store = JobStore()
    started = asyncio.Event()
    release = asyncio.Event()

    async def runner(req):
        started.set()
        await release.wait()
        return _ok(req)

    rec = store.submit(_req(), runner)
    await started.wait()
    dropped = store.reap(now=10_000_000.0)
    assert dropped == 0
    assert store.get(rec.task_id) is not None
    release.set()
    await rec.task
