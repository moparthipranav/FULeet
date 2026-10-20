from contextlib import asynccontextmanager

import pytest

from app.core import database, redis as redis_module
from app.main import app, lifespan


@pytest.mark.asyncio
async def test_database_dependency_closes_session(monkeypatch):
    class FakeSession:
        closed = False

        async def close(self):
            self.closed = True

    class FakeSessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *_):
            return None

    session = FakeSession()
    monkeypatch.setattr(
        database,
        "AsyncSessionLocal",
        lambda: FakeSessionContext(session),
    )

    dependency = database.get_db()
    assert await anext(dependency) is session
    await dependency.aclose()

    assert session.closed is True


@pytest.mark.asyncio
async def test_redis_dependency_closes_client(monkeypatch):
    class FakeRedis:
        closed = False

        async def aclose(self):
            self.closed = True

    client = FakeRedis()
    monkeypatch.setattr(redis_module.aioredis, "Redis", lambda **_: client)

    dependency = redis_module.get_redis()
    assert await anext(dependency) is client
    await dependency.aclose()

    assert client.closed is True


@pytest.mark.asyncio
async def test_application_lifespan_disposes_pools(monkeypatch):
    state = {"disposed": False, "redis_disconnected": False, "schema_started": False}

    class FakeConnection:
        async def run_sync(self, _callback):
            state["schema_started"] = True

    class FakeEngine:
        @asynccontextmanager
        async def begin(self):
            yield FakeConnection()

        async def dispose(self):
            state["disposed"] = True

    class FakeRedisPool:
        async def disconnect(self):
            state["redis_disconnected"] = True

    monkeypatch.setattr("app.main.engine", FakeEngine())
    monkeypatch.setattr("app.main.redis_pool", FakeRedisPool())

    async with lifespan(app):
        assert state["schema_started"] is True

    assert state["disposed"] is True
    assert state["redis_disconnected"] is True
