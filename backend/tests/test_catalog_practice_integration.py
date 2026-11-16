"""Catalog, capabilities, dashboard and history against real PostgreSQL (_test database)."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from test_auth_integration import bearer, make_settings, new_account
from test_database_integration import alembic
from test_schema_integrity import add, attempt, change, exercise

from app.core.config import Settings
from app.db import models as m
from app.main import create_app
from app.modules.catalog.seed import seed
from app.modules.catalog.seed_data import PERSONAS, TOPICS

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("RUN_DB_TESTS") != "1", reason="Set RUN_DB_TESTS=1 to opt in"),
]


@pytest.fixture(scope="module")
def engine():
    settings = make_settings()
    alembic("upgrade", "head")
    db = create_engine(settings.database_url, hide_parameters=True)
    yield db
    db.dispose()


@pytest.fixture
def client(engine):
    with TestClient(create_app(make_settings())) as test_client:
        yield test_client


def user_id(client, tokens) -> UUID:
    return UUID(client.get("/api/v1/users/me", headers=bearer(tokens)).json()["user_id"])


def make_attempt(engine, owner: UUID, status: str, activity: datetime, score=None) -> UUID:
    """Committed writing attempt in the requested state, with consistent timestamps."""
    with engine.begin() as conn:
        eid, _ = exercise(conn, owner=owner)
        aid = attempt(conn, eid, owner)
        started = activity - timedelta(minutes=10)
        change(conn, m.Attempt, aid, started_at=started, last_activity_at=activity)
        if status != "in_progress":
            change(
                conn,
                m.WritingAttempt,
                aid,
                response_text="Yesterday I went to school with my friend.",
            )
            change(
                conn,
                m.Attempt,
                aid,
                status="submitted",
                submitted_at=activity,
                current_stage="evaluation",
            )
        if status in ("evaluating", "completed", "failed"):
            ev = add(conn, m.Evaluation, attempt_id=aid, rubric_version="v1", rubric_snapshot={})
            change(conn, m.Attempt, aid, status="evaluating", current_stage="evaluation")
            if status == "completed":
                change(
                    conn,
                    m.Evaluation,
                    ev,
                    status="completed",
                    completed_at=activity,
                    overall_score=score,
                    max_score=None if score is None else 9,
                )
                change(
                    conn,
                    m.Attempt,
                    aid,
                    status="completed",
                    completed_at=activity,
                    current_stage="results",
                )
            elif status == "failed":
                change(conn, m.Evaluation, ev, status="failed")
                change(conn, m.Attempt, aid, status="failed")
    return aid


# --- Catalog -----------------------------------------------------------------------


def test_seed_is_repeatable_and_lists_are_public_safe(client, engine) -> None:
    settings = Settings()
    assert asyncio.run(seed(settings)) == (len(TOPICS), len(PERSONAS))
    assert asyncio.run(seed(settings)) == (len(TOPICS), len(PERSONAS))  # idempotent
    with engine.begin() as conn:
        hidden = add(conn, m.Topic, name=f"Hidden {uuid4()}", is_active=False)

    _, tokens = new_account(client)
    topics = client.get("/api/v1/topics?limit=100", headers=bearer(tokens)).json()
    names = [t["name"] for t in topics["items"]]
    assert {name for _, name, _ in TOPICS} <= set(names)
    assert names == sorted(names)
    assert str(hidden) not in {t["topic_id"] for t in topics["items"]}
    assert set(topics["items"][0]) == {"topic_id", "name", "description"}

    personas = client.get("/api/v1/personas?limit=100", headers=bearer(tokens)).json()
    assert {name for _, name, *_ in PERSONAS} <= {p["name"] for p in personas["items"]}
    for persona in personas["items"]:
        assert set(persona) == {"persona_id", "name", "role_description"}
    assert "behavior" not in str(personas) and "voice" not in str(personas)


def test_topic_pagination_walks_every_row_once(client) -> None:
    _, tokens = new_account(client)
    everything = client.get("/api/v1/topics?limit=100", headers=bearer(tokens)).json()["items"]
    seen, cursor = [], None
    while True:
        url = "/api/v1/topics?limit=3" + (f"&cursor={cursor}" if cursor else "")
        page = client.get(url, headers=bearer(tokens)).json()
        assert len(page["items"]) <= 3
        seen += page["items"]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == everything


@pytest.mark.parametrize("path", ["/api/v1/topics", "/api/v1/personas", "/api/v1/capabilities"])
def test_catalog_requires_session(client, path: str) -> None:
    assert client.get(path).status_code == 401


def test_bad_paging_parameters(client) -> None:
    _, tokens = new_account(client)
    for query in ("limit=0", "limit=101", "cursor=garbage", "cursor=e30"):
        response = client.get(f"/api/v1/topics?{query}", headers=bearer(tokens))
        assert response.status_code == 422, query


def test_capabilities(client) -> None:
    _, tokens = new_account(client)
    body = client.get("/api/v1/capabilities", headers=bearer(tokens)).json()
    assert body["speaking"] == {"live_transcription": False, "pronunciation_assessment": False}
    assert body["limits"]["max_request_bytes"] == client.app.state.settings.max_request_bytes


# --- Dashboard and history ---------------------------------------------------------


def test_dashboard_for_new_user_is_empty(client) -> None:
    _, tokens = new_account(client)
    body = client.get("/api/v1/dashboard", headers=bearer(tokens)).json()
    assert body["resume_attempt"] is None
    assert body["pending_attempts"] == []
    assert body["has_more_pending"] is False
    assert body["user"]["user_id"] == str(user_id(client, tokens))


def test_dashboard_resume_pending_and_isolation(client, engine) -> None:
    _, tokens = new_account(client)
    _, other = new_account(client)
    me, them = user_id(client, tokens), user_id(client, other)
    now = datetime.now(UTC)
    older_draft = make_attempt(engine, me, "in_progress", now - timedelta(hours=2))
    newest_draft = make_attempt(engine, me, "in_progress", now - timedelta(hours=1))
    make_attempt(engine, them, "in_progress", now)  # someone else's, more recent
    pending = [make_attempt(engine, me, "submitted", now - timedelta(minutes=i)) for i in range(11)]
    make_attempt(engine, me, "completed", now, score=7)

    body = client.get("/api/v1/dashboard", headers=bearer(tokens)).json()
    assert body["resume_attempt"]["attempt_id"] == str(newest_draft)
    assert body["resume_attempt"]["status"] == "in_progress"
    assert body["resume_attempt"]["skill"] == "writing"
    assert body["resume_attempt"]["title"] == "Travel practice"
    assert [a["attempt_id"] for a in body["pending_attempts"]] == [str(a) for a in pending[:10]]
    assert body["has_more_pending"] is True
    assert str(older_draft) not in str(body["pending_attempts"])


def test_attempt_history_filters_scores_and_pages(client, engine) -> None:
    _, tokens = new_account(client)
    _, other = new_account(client)
    me = user_id(client, tokens)
    now = datetime.now(UTC)
    scored = make_attempt(engine, me, "completed", now - timedelta(minutes=1), score=6.5)
    unscored = make_attempt(engine, me, "completed", now - timedelta(minutes=2))
    failed = make_attempt(engine, me, "failed", now - timedelta(minutes=3))
    draft = make_attempt(engine, me, "in_progress", now - timedelta(minutes=4))
    make_attempt(engine, user_id(client, other), "completed", now, score=9)

    items = client.get("/api/v1/attempts", headers=bearer(tokens)).json()["items"]
    assert [i["attempt_id"] for i in items] == [str(a) for a in (scored, unscored, failed, draft)]
    assert items[0]["score"] == {"value": 6.5, "max": 9.0}
    assert items[1]["score"] is None  # completed without a valid score stays null
    assert items[2]["score"] is None

    completed = client.get("/api/v1/attempts?status=completed", headers=bearer(tokens)).json()
    assert [i["attempt_id"] for i in completed["items"]] == [str(scored), str(unscored)]
    empty = client.get("/api/v1/attempts?skill=reading", headers=bearer(tokens)).json()
    assert empty == {"items": [], "next_cursor": None}

    first = client.get("/api/v1/attempts?limit=3", headers=bearer(tokens)).json()
    assert len(first["items"]) == 3 and first["next_cursor"]
    second = client.get(
        f"/api/v1/attempts?limit=3&cursor={first['next_cursor']}", headers=bearer(tokens)
    ).json()
    assert [i["attempt_id"] for i in second["items"]] == [str(draft)]
    assert second["next_cursor"] is None

    # The cursor is bound to its filters and its owner.
    other_filter = client.get(
        f"/api/v1/attempts?status=failed&cursor={first['next_cursor']}", headers=bearer(tokens)
    )
    assert other_filter.status_code == 422
    stolen = client.get(f"/api/v1/attempts?cursor={first['next_cursor']}", headers=bearer(other))
    assert stolen.status_code == 422

    assert client.get("/api/v1/attempts?status=bogus", headers=bearer(tokens)).status_code == 422


def test_request_body_limit(engine) -> None:
    with TestClient(create_app(make_settings(max_request_bytes=64 * 1024))) as client:
        _, tokens = new_account(client)
        huge = {"display_name": "x" * (70 * 1024)}
        response = client.patch("/api/v1/users/me", headers=bearer(tokens), json=huge)
        assert response.status_code == 413
        assert response.json()["code"] == "CAPACITY_EXCEEDED"
        assert response.json()["request_id"] == response.headers["X-Request-ID"]

        def chunks():
            yield b'{"display_name": "'
            yield b"x" * (70 * 1024)
            yield b'"}'

        chunked = client.patch(
            "/api/v1/users/me",
            headers={**bearer(tokens), "Content-Type": "application/json"},
            content=chunks(),
        )
        assert chunked.status_code == 413
