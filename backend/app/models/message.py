import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class Message(SQLModel):
    message: str

class LLMConversation(SQLModel, table=True):
    __tablename__ = "llm_conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(nullable=False)
    title: str = Field(nullable=False)
    created_at: datetime = Field(nullable=False)
    updated_at: datetime = Field(nullable=False)
    file_urls: list[dict[str, Any]] = Field(sa_column=Column(JSONB, nullable=False))
    messages: list[dict[str, Any]] = Field(sa_column=Column(JSONB, nullable=False))
    model_name: str | None = Field(nullable=True, max_length=100)
    total_tokens: int | None = Field(nullable=True)
    meta_data: dict[str, Any] | None = Field(
        sa_column=Column("metadata", JSONB, nullable=True)
    )
