"""Upsert the starter catalog. Safe to run repeatedly.

Local:  make seed
Docker: docker compose --profile full run --rm migrate python -m app.modules.catalog.seed

Rows are matched by fixed IDs and refreshed from seed_data. Rows not listed there
(added by hand or deactivated) are left untouched.
"""

import asyncio

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.modules.catalog.models import AIPersona, Topic
from app.modules.catalog.seed_data import PERSONAS, TOPICS, stable_id


async def seed(settings: Settings) -> tuple[int, int]:
    engine = create_async_engine(settings.database_url, hide_parameters=True)
    topics = [
        {"topic_id": stable_id("topic", slug), "name": name, "description": description}
        for slug, name, description in TOPICS
    ]
    personas = [
        {
            "persona_id": stable_id("persona", slug),
            "name": name,
            "role_description": role,
            "behavior_instructions": behavior,
            "voice_key": voice,
        }
        for slug, name, role, behavior, voice in PERSONAS
    ]
    try:
        async with engine.begin() as connection:
            statement = insert(Topic).values(topics)
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[Topic.topic_id],
                    set_={
                        "name": statement.excluded.name,
                        "description": statement.excluded.description,
                    },
                )
            )
            statement = insert(AIPersona).values(personas)
            await connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[AIPersona.persona_id],
                    set_={
                        column: statement.excluded[column]
                        for column in (
                            "name",
                            "role_description",
                            "behavior_instructions",
                            "voice_key",
                        )
                    },
                )
            )
    finally:
        await engine.dispose()
    return len(topics), len(personas)


if __name__ == "__main__":
    topic_count, persona_count = asyncio.run(seed(Settings()))
    print(f"Seeded {topic_count} topics and {persona_count} personas.")
