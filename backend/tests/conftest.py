import os
import uuid
import json
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@127.0.0.1:1/fleet_test",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")

from app.core.database import Base, get_db
from app.core.redis import get_redis
from app.main import app
from app.sandbox.base import ExecutionResult, SandboxUnavailableError
from app.api import execution as execution_api
from app.services import evaluator


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.fail_get = False
        self.fail_set = False

    async def get(self, name: str):
        if self.fail_get:
            raise RedisConnectionError("Redis unavailable")
        return self.values.get(name)

    async def set(self, name: str, value: str, ex: int):
        if self.fail_set:
            raise RedisConnectionError("Redis unavailable")
        self.values[name] = value
        self.expirations[name] = ex
        return True


class FakePistonRunner:
    def __init__(self):
        self.calls: list[dict] = []

    async def execute(
        self,
        language: str,
        source_code: str,
        stdin_data: str,
        time_limit_ms: int = 2000,
        memory_limit_kb: int = 262144,
    ) -> ExecutionResult:
        self.calls.append(
            {
                "language": language,
                "source_code": source_code,
                "stdin_data": stdin_data,
                "time_limit_ms": time_limit_ms,
                "memory_limit_kb": memory_limit_kb,
            }
        )
        if "SANDBOX_UNAVAILABLE" in source_code:
            raise SandboxUnavailableError("Piston execution service is unavailable")
        if "COMPILATION_ERROR" in source_code:
            return ExecutionResult("", "SyntaxError: invalid syntax", 1, 0, 0, compilation_error=True)
        if "ZERO_DIVISION" in source_code:
            return ExecutionResult(
                "",
                "Traceback (most recent call last):\nZeroDivisionError: division by zero",
                1,
                4,
                0,
            )
        if "INFINITE_LOOP" in source_code:
            return ExecutionResult("", "Execution timed out", 1, time_limit_ms, 0, timed_out=True)
        if "SLOW" in source_code:
            return ExecutionResult("", "", 0, time_limit_ms + 1, 0)
        if "WRONG_ANSWER" in source_code:
            return ExecutionResult("[0, 0]\n", "", 0, 4, 0)

        numbers, target = stdin_data.splitlines()
        numbers = json.loads(numbers)
        target = int(target)
        answer = next(
            [left, right]
            for left in range(len(numbers))
            for right in range(left + 1, len(numbers))
            if numbers[left] + numbers[right] == target
        )
        return ExecutionResult(json.dumps(answer) + "\n", "", 0, 4, 0)


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncIterator[AsyncSession]:
    connection = await test_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.fixture
def redis_client():
    return FakeRedis()


@pytest.fixture
def piston_runner(monkeypatch):
    runner = FakePistonRunner()
    monkeypatch.setattr(execution_api, "piston_runner", runner)
    monkeypatch.setattr(evaluator, "piston_runner", runner)
    return runner


@pytest_asyncio.fixture
async def client(db_session, redis_client, piston_runner) -> AsyncIterator[AsyncClient]:
    async def override_redis():
        return redis_client

    app.dependency_overrides[get_redis] = override_redis
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client
    app.dependency_overrides.pop(get_redis, None)
