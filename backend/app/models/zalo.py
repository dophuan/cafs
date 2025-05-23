from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class ZaloConversationBase(SQLModel):
    conversation_id: str
    group_id: str | None = None
    sender_id: str
    event_type: str
    message_text: str | None = None
    file_url: str | None = None
    file_name: str | None = None
    file_type: str | None = None
    sticker_id: str | None = None
    sticker_url: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    llm_analysis: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    raw_payload: dict[str, Any] = Field(sa_column=Column(JSONB))

class ZaloConversation(ZaloConversationBase, table=True):
    __tablename__ = "zalo_conversations"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )

class ZaloConversationCreate(ZaloConversationBase):
    pass

class ZaloConversationRead(ZaloConversationBase):
    id: int
    created_at: datetime
