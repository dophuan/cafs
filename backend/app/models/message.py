import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, validator
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

class MessageContent(BaseModel):
    role: str
    content: str

    @validator("role")
    def validate_role(cls, v: str) -> str:
        if v not in ["user", "assistant"]:
            raise ValueError('Role must be either "user" or "assistant"')
        return v

class ChatRequest(BaseModel):
    user_message: str | list[MessageContent]

class ChatResponse(BaseModel):
    bot_response: str
    conversation_id: str | None = None

class ConversationRequest(BaseModel):
    group_id: str
    response_text: str

class GroupMessageRequest(BaseModel):
    group_id: str
    text: str

class InventoryActionRequest(BaseModel):
    message: str
    action: str

class ConversationWithInventoryRequest(BaseModel):
    conversation: ConversationRequest
    inventory_action: InventoryActionRequest
