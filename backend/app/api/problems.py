"""
This API endpoints should the following tasks:
1. List all the problems 
3. Creating / seeding a problem
4. get single problem workspace + saved drafts
5. Continuous Auto-save draft endpoint
6. Toggle favourite/solve again 
"""

import logging
import uuid
from fastapi import APIRouter
from fastapi import Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import func
from typing import Any, List, Optional, cast
import redis.asyncio as aioredis
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.database import get_db
from app.core.redis import get_redis
from app.models.entities import (
    LanguageTemplate,
    Problem,
    TestCase,
    User,
    UserDraft,
    UserProblemStatus,
)

from app.schemas.workspace import ( # Pydantic schemes represent the network boundary (what comes in over HTTP requests and what goes out in HTTP requests)
    BookmarkToggleRequest,
    DraftSaveRequest,
    ProblemCreate,
    ProblemListItem,
    ProblemWorkspaceResponse
)


router = APIRouter(prefix="/api/v1", tags=["Workspace & Problems"])
logger = logging.getLogger(__name__)


def _dialect_insert(db: AsyncSession, table):
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "sqlite":
        return sqlite_insert(table)
    if dialect_name == "postgresql":
        return pg_insert(table)
    raise RuntimeError(f"Unsupported database dialect for upsert: {dialect_name}")

# 1. Create a DEMO user (for testing the foreign keys)
@router.post("/users/demo")
async def create_demo_user(username: str = "pranav", db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(User).where(User.username == username))
    if existing:
        return {"user_id": existing.user_id, "username": existing.username}

    user = User(
        username=username,
        email=f"{username}@gmail.com",
        password_hash="hashed_dummy_password",
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"user_id": user.user_id, "username": user.username}

# 2. CREATE / SEED a problem (FR1 & FR5)
@router.post("/problems", status_code=201)
async def create_problem(payload: ProblemCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.scalar(select(Problem).where(Problem.slug == payload.slug))
    if existing:
        raise HTTPException(status_code=400, detail="Problem slug already exists")

    problem = Problem(
        slug=payload.slug,
        title=payload.title,
        difficulty=payload.difficulty,
        prob_description=payload.prob_description,
        prob_image_url=payload.prob_image_url,
        prob_examples=payload.prob_examples,
        prob_constraints=payload.prob_constraints,
        time_limit_ms=payload.time_limit_ms,
        memory_limit_kb=payload.memory_limit_kb,
    )   

    db.add(problem)
    await db.flush() # Generated problem.problem_id before commiting

    for tpl in payload.language_templates:
        db.add(
            LanguageTemplate(
                problem_id=problem.problem_id,
                template_language=tpl.template_language,
                boilerplate=tpl.boilerplate,
                driver_harness=tpl.driver_harness,
            )
        )
    
    for tc in payload.test_cases:
        db.add(
            TestCase(
                problem_id=problem.problem_id,
                expected_input=tc.expected_input,
                expected_output=tc.expected_output,
                is_sample=tc.is_sample,
                ordinal_order=tc.ordinal_order,
            )
        )

    await db.commit()
    return {"problem_id": problem.problem_id, "slug": problem.slug}

# 3. List all the problems with the user status (FR1 & FR4)
@router.get("/problems", response_model=List[ProblemListItem])
async def list_problems(
    user_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Problem).order_by(Problem.created_at))
    problems = result.scalars().all()

    status_map = {}
    if user_id:
        statuses = await db.execute(
            select(UserProblemStatus).where(UserProblemStatus.user_id == user_id)
        )
        for s in statuses.scalars().all():
            status_map[s.problem_id] = s


    response = []

    for p in problems:
        st = status_map.get(p.problem_id)
        response.append(
            ProblemListItem(
                problem_id=p.problem_id,
                slug=p.slug,
                title=p.title,
                difficulty=p.difficulty,
                status=st.status if st else None,
                is_favourite=st.is_favourite if st else False,
                solve_again=st.solve_again if st else False,
            )
        )

    return response

# 4. GET single problem workspace + saved drafts (FR1, FR4, FR5)
@router.get("/problems/{slug}", response_model=ProblemWorkspaceResponse)
async def get_problem_workspace(
    slug:str,
    user_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):

    stmt = (
        select(Problem)
        .where(Problem.slug == slug)
        .options(
            selectinload(Problem.language_templates),
            selectinload(Problem.test_cases),
        )
    )

    problem = await db.scalar(stmt)
    if not problem:
        raise HTTPException(status_code=404, detail="Problem Not Found")

    sample_test_cases = [tc for tc in problem.test_cases if tc.is_sample]

    # Loading the user's drafts (Checking Redis first, fallback to postgres)
    saved_drafts: dict[str, str] = {}
    if user_id:
        db_drafts = await db.execute(
            select(UserDraft).where(
                UserDraft.user_id == user_id,
                UserDraft.problem_id == problem.problem_id,
            )
        )

        for d in db_drafts.scalars().all():
            saved_drafts[d.language] = d.code

        for tpl in problem.language_templates:
            lang = tpl.template_language
            redis_key = f"draft:{user_id}:{problem.problem_id}:{lang}"
            try:
                cached_code = await redis_client.get(name=redis_key)
            except aioredis.RedisError:
                logger.warning("Redis draft lookup failed; using PostgreSQL draft")
                continue
            if cached_code is not None:
                saved_drafts[lang] = (
                    cached_code.decode("utf-8")
                    if isinstance(cached_code, bytes)
                    else cached_code
                )

    return ProblemWorkspaceResponse(
        problem_id=problem.problem_id,
        slug=problem.slug,
        title=problem.title,
        difficulty=problem.difficulty,
        prob_description=problem.prob_description,
        prob_image_url=problem.prob_image_url,
        prob_examples=cast(List[dict[str, Any]], problem.prob_examples),
        prob_constraints=problem.prob_constraints,
        time_limit_ms=problem.time_limit_ms,
        memory_limit_kb=problem.memory_limit_kb,
        language_templates=cast(List[Any], problem.language_templates),
        sample_test_cases=cast(List[Any], sample_test_cases),
        saved_drafts=saved_drafts,
    )


# 5. Continuous AUTO-SAVE Draft endpoint
@router.put("/problems/{slug}/draft")
async def save_code_draft(
    slug: str,
    payload: DraftSaveRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis)
):
    problem_id = await db.scalar(
        select(Problem.problem_id).where(Problem.slug == slug)
    )

    if not problem_id:
        raise HTTPException(status_code=404, detail="Problem not found")

    user = await db.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    stmt = (
        _dialect_insert(db, UserDraft)
        .values(
            user_id=payload.user_id,
            problem_id=problem_id,
            language=payload.language,
            code=payload.code,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "problem_id", "language"],
            set_={"code": payload.code, "updated_at": func.now()},
        )
    )
    await db.execute(stmt)
    await db.commit()

    redis_key = f"draft:{payload.user_id}:{problem_id}:{payload.language}"
    try:
        await redis_client.set(redis_key, payload.code, ex=86400)
    except aioredis.RedisError:
        logger.warning("Redis draft cache write failed; PostgreSQL draft was saved")

    return {"status": "saved", "language": payload.language}


@router.patch("/problems/{slug}/bookmark")
async def toggle_bookmark(
    slug: str,
    payload: BookmarkToggleRequest,
    db: AsyncSession = Depends(get_db),
):
    problem_id = await db.scalar(
        select(Problem.problem_id).where(Problem.slug == slug)
    )
    if not problem_id:
        raise HTTPException(status_code=404, detail="Problem not found")

    user_id = await db.scalar(
        select(User.user_id).where(User.user_id == payload.user_id)
    )
    if not user_id:
        raise HTTPException(status_code=404, detail="User not found")

    values = {
        "user_id": payload.user_id,
        "problem_id": problem_id,
        "status": None,
        "is_favourite": bool(payload.is_favourite),
        "solve_again": bool(payload.solve_again),
    }
    updates = {}
    if payload.is_favourite is not None:
        updates["is_favourite"] = payload.is_favourite
    if payload.solve_again is not None:
        updates["solve_again"] = payload.solve_again
    if not updates:
        updates["user_id"] = UserProblemStatus.user_id

    stmt = (
        _dialect_insert(db, UserProblemStatus)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["user_id", "problem_id"],
            set_=updates,
        )
    )
    await db.execute(stmt)

    await db.commit()
    existing = await db.scalar(
        select(UserProblemStatus).where(
            UserProblemStatus.user_id == payload.user_id,
            UserProblemStatus.problem_id == problem_id,
        ).execution_options(populate_existing=True)
    )
    if existing is None:
        raise RuntimeError("Problem status was not available after the upsert")
    return {
        "problem_id": problem_id,
        "is_favourite": existing.is_favourite,
        "solve_again": existing.solve_again,
    }