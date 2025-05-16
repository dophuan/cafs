from typing import List, Optional
from sqlmodel import Session, select
from fastapi import HTTPException
import hmac
import hashlib

from app.models.webhook import Webhook, WebhookCreate, WebhookRead
from app.core.config import settings

class WebhookService:
    def __init__(self, db: Session):
        self.db = db

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature using HMAC"""
        if not settings.WEBHOOK_SECRET_KEY:
            return True
        
        # Debug prints
        print("Server Secret Key:", settings.WEBHOOK_SECRET_KEY)
        print("Received Signature:", signature)
        print("Received Payload:", payload.decode('utf-8'))
        
        expected_signature = hmac.new(
            settings.WEBHOOK_SECRET_KEY.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        print("Expected Signature:", expected_signature)
        
        return expected_signature == signature

    def create_webhook(self, webhook_data: WebhookCreate) -> Webhook:
        """Create a new webhook entry"""
        db_webhook = Webhook.from_orm(webhook_data)
        self.db.add(db_webhook)
        self.db.commit()
        self.db.refresh(db_webhook)
        return db_webhook

    def get_webhooks(self, skip: int = 0, limit: int = 100) -> List[Webhook]:
        """Get list of webhooks with pagination"""
        statement = select(Webhook).offset(skip).limit(limit)
        return self.db.exec(statement).all()

    def get_webhook_by_id(self, webhook_id: int) -> Optional[Webhook]:
        """Get a specific webhook by ID"""
        statement = select(Webhook).where(Webhook.id == webhook_id)
        return self.db.exec(statement).first()

    def get_webhooks_by_event_type(
        self, event_type: str, skip: int = 0, limit: int = 100
    ) -> List[Webhook]:
        """Get webhooks filtered by event type"""
        statement = (
            select(Webhook)
            .where(Webhook.event_type == event_type)
            .offset(skip)
            .limit(limit)
        )
        return self.db.exec(statement).all()

    def process_webhook_payload(self, payload_json: dict) -> WebhookCreate:
        """Process and validate webhook payload"""
        try:
            # Map event_name to event_type if it exists, otherwise fallback to event_type or unknown
            event_type = payload_json.get("event_name") or payload_json.get("event_type", "unknown")
            
            return WebhookCreate(
                event_type=event_type,
                payload=payload_json
            )
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid payload format: {str(e)}"
            )