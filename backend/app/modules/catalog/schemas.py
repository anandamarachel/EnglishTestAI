from uuid import UUID

from pydantic import BaseModel


class TopicOut(BaseModel):
    topic_id: UUID
    name: str
    description: str | None


class PersonaOut(BaseModel):
    """Public fields only: behavior instructions and voice keys stay server-side."""

    persona_id: UUID
    name: str
    role_description: str


class TopicPage(BaseModel):
    items: list[TopicOut]
    next_cursor: str | None


class PersonaPage(BaseModel):
    items: list[PersonaOut]
    next_cursor: str | None
