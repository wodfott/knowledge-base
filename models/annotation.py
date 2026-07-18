"""Personal Memory models: annotations and review records."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Annotation(BaseModel):
    """A personal annotation on a document, entity, or relation."""
    id: str
    target_type: str  # "document", "entity", "relation"
    target_id: str
    annotation_type: str  # "highlight", "note", "link", "rating"
    content: str
    linked_entity_id: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ReviewRecord(BaseModel):
    """An Anki-simplified review record."""
    id: str
    entity_id: str
    ease: float = Field(default=2.5, ge=1.3)
    interval_days: int = 1
    repetitions: int = 0
    last_reviewed: Optional[datetime] = None
    next_review: datetime = Field(default_factory=datetime.now)
    created_at: datetime = Field(default_factory=datetime.now)
