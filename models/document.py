"""Document models for collected content."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Document(BaseModel):
    """A collected and normalized document."""
    id: str = Field(..., description="Unique document ID (hash-based)")
    title: str
    content: str
    source_type: str  # "web", "rss", "feishu_doc", "obsidian", "manual"
    source_url: Optional[str] = None
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    """A chunk of a document for embedding and retrieval."""
    id: str
    doc_id: str
    chunk_index: int
    content: str
    token_count: int = 0
    embedding: Optional[list[float]] = None
