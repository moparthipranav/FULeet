from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from app.core.database import Base, engine, get_db
from app.core.redis import redis_pool, get_redis
import app.models.entities  # IMPORTANT: registers models with Base.metadata
from app.api.problems import router as problems_router
from app.api.execution import router as execution_router
from app.sandbox.base import SandboxUnavailableError



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Automatically create all 7 tables in PostgreSQL 18 if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    await redis_pool.disconnect()


app = FastAPI(
    title="DSA AI Platform API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(problems_router)
app.include_router(execution_router)


@app.exception_handler(SandboxUnavailableError)
async def sandbox_unavailable_handler(_, exc: SandboxUnavailableError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
    )


@app.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    result = await db.execute(text("SELECT 1"))
    pong = await redis_client.ping()
    return {
        "status": "ok",
        "postgres": result.scalar() == 1,
        "redis": bool(pong),
    }