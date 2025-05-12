from datetime import datetime
from typing import Dict, Any, Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON

class WebhookBase(SQLModel):
    event_type: str = Field(index=True)
    # Use SQLAlchemy JSON type for the payload field
    payload: Dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON)
    )

class Webhook(WebhookBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WebhookCreate(WebhookBase):
    pass

class WebhookRead(WebhookBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True