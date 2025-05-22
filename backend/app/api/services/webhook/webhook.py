from typing import List, Optional, Dict, Any
from app.api.services.zalo.zalo_interaction import ZaloInteractionService
from app.api.constants.actions import CHECK_STOCK_LEVELS, NORMAL_CONVERSATION, SEARCH_PRODUCTS
from sqlmodel import Session, select
from fastapi import HTTPException
import hmac
import hashlib
import logging

from app.models.webhook import Webhook, WebhookCreate
from app.core.config import settings
from app.api.services.conversation.chat import LLMService
from app.api.services.webhook.base import BaseWebhookService
from app.api.services.zalo.zalo_parser import ZaloParser
from app.api.services.conversation.conversation import ConversationService
from app.api.services.webhook.inventory import InventoryService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, db: Session, llm_service: LLMService | None = None):
        self.db = db
        self.llm_service = llm_service or LLMService(
            db=db,
            api_key=settings.OPENAI_API_KEY,
            engine=settings.OPENAI_ENGINE
        )
        # Initialize utilities
        self.base_handler = BaseWebhookService(db)
        self.zalo_parser = ZaloParser()
        self.conversation_handler = ConversationService(db, llm_service)
        self.inventory_handler = InventoryService(db)
        self.zalo_service = ZaloInteractionService()

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature using HMAC"""
        if not settings.WEBHOOK_SECRET_KEY:
            return True
        
        expected_signature = hmac.new(
            settings.WEBHOOK_SECRET_KEY.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        logger.info(f"Received signature: {signature}")
        logger.info(f"Expected signature: {expected_signature}")
        logger.info(f"Payload: {payload.decode()}")
        
        return expected_signature == signature

    async def create_webhook(self, webhook_data: WebhookCreate) -> Webhook:
        """Create a new webhook entry"""
        try:
            await self.inventory_handler.sync_products_to_elasticsearch()
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

    async def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Main webhook processing method using utilities"""
        try:
            # 1. Parse Zalo message
            event_type, parsed_data = self.zalo_parser.parse_message(payload)
            
            # 2. Store conversation and get intent analysis
            conversation_result = await self.conversation_handler.process_conversation(
                event_type,
                parsed_data
            )

            result = {
                "status": "success",
                "conversation_id": conversation_result.get("conversation_id"),
                "event_type": event_type
            }

            final_intent = conversation_result.get("intent")
            if final_intent:
                final_intent["parameters"]["query"] = payload.get("message", {}).get("text")
            intent_type = final_intent.get("intent") if final_intent else None

            # Handle normal conversation response
            if intent_type == NORMAL_CONVERSATION:
                zalo_result = await self.zalo_service.handle_normal_conversation(conversation_result)
                result.update(zalo_result)

            elif intent_type in [CHECK_STOCK_LEVELS, SEARCH_PRODUCTS]:
                inventory_action = await self.inventory_handler.handle_inventory_action(final_intent)
                zalo_result = await self.zalo_service.handle_inventory_response(
                    conversation_result,
                    inventory_action
                )
                result.update(zalo_result)
                result["inventory_action"] = inventory_action
            
            # Handle inventory actions
            elif final_intent:
                inventory_action = await self.inventory_handler.handle_inventory_action(
                    final_intent
                )
                result["inventory_action"] = inventory_action

            return result

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error processing webhook: {str(e)}"
            )
