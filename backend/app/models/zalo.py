from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, DateTime, func
from sqlmodel import SQLModel, Field
from sqlalchemy.dialects.postgresql import JSONB

class ZaloConversationBase(SQLModel):
    conversation_id: str
    group_id: Optional[str] = None
    sender_id: str
    event_type: str
    message_text: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    sticker_id: Optional[str] = None
    sticker_url: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    llm_analysis: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    raw_payload: Dict[str, Any] = Field(sa_column=Column(JSONB))

class ZaloConversation(ZaloConversationBase, table=True):
    __tablename__ = "zalo_conversations"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), server_default=func.now())
    )

class ZaloConversationCreate(ZaloConversationBase):
    pass

class ZaloConversationRead(ZaloConversationBase):
    id: int
    created_at: datetime