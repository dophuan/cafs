from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class WebhookBase(SQLModel):
    event_type: str = Field(index=True)
    payload: dict[str, Any] = Field(
        default={},
        sa_column=Column(JSON)
    )

class Webhook(WebhookBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class WebhookCreate(WebhookBase):
    pass

class WebhookRead(WebhookBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
