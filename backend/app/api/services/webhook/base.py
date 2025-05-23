import hashlib
import hmac

from fastapi import HTTPException
from sqlmodel import Session

from app.core.config import settings
from app.models.webhook import Webhook, WebhookCreate


class BaseWebhookService:
    def __init__(self, db: Session):
        self.db = db

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        if not settings.WEBHOOK_SECRET_KEY:
            return True

        expected_signature = hmac.new(
            settings.WEBHOOK_SECRET_KEY.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        return expected_signature == signature

    def store_webhook(self, webhook_data: WebhookCreate) -> Webhook:
        try:
            db_webhook = Webhook.from_orm(webhook_data)
            self.db.add(db_webhook)
            self.db.commit()
            self.db.refresh(db_webhook)
            return db_webhook
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Database error: {str(e)}"
            )
