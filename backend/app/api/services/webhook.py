from typing import List, Optional, Dict, Any
from sqlmodel import Session, select
from fastapi import HTTPException
import hmac
import hashlib
import json
import logging

from app.models.webhook import Webhook, WebhookCreate, WebhookRead
from app.core.config import settings
from app.api.services.chat import LLMService
from app.api.services.webhook_utils.base import BaseWebhookService
from app.api.services.webhook_utils.zalo_parser import ZaloParser
from app.api.services.webhook_utils.conversation import ConversationService
from app.api.services.webhook_utils.inventory import InventoryService

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

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature using HMAC"""
        if not settings.WEBHOOK_SECRET_KEY:
            return True
        
        expected_signature = hmac.new(
            settings.WEBHOOK_SECRET_KEY.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return expected_signature == signature

    def create_webhook(self, webhook_data: WebhookCreate) -> Webhook:
        """Create a new webhook entry"""
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
            
            # Handle normal conversation response
            if (final_intent.get("intent") == "NORMAL_CONVERSATION" and 
                conversation_result.get("response_text") and 
                conversation_result.get("group_id")):
                
                group_id=conversation_result["group_id"],
                text=conversation_result["response_text"]
                print(f"Group id: {group_id}")
                print(f"Response text: {text}")
                # Send response back to Zalo group
                await self.llm_service.send_group_message(
                    group_id=conversation_result["group_id"],
                    text=conversation_result["response_text"]
                )
                result["response_sent"] = True
            
            # Handle inventory actions
            elif final_intent:
                inventory_action = await self.inventory_handler.handle_inventory_action(
                    final_intent
                )
                logger.info(f"LOGS the action {inventory_action}")
                result["inventory_action"] = inventory_action

            return result

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error processing webhook: {str(e)}"
            )

    async def process_zalo_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Zalo event with LLM and determine action"""
        event_name = payload.get("event_name", "unknown")
        
        system_prompt = """You are an AI assistant helping to process Zalo messaging events. 
        Analyze the event and provide a structured response with:
        1. Event Type Summary
        2. Key Information Extracted
        3. Recommended Action
        Format your response as JSON with these keys: summary, extracted_info, recommended_action"""

        event_prompt = f"""
        Event Name: {event_name}
        Full Payload: {payload}
        
        Please analyze this Zalo event and provide structured guidance for handling it.
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": event_prompt}
        ]

        try:
            llm_response = self.llm_service.query(messages)
            analysis = json.loads(llm_response)
            
            response = await self.handle_event_type(event_name, payload, analysis)
            
            return response

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error LLM processing Zalo event: {str(e)}"
            )

    async def handle_event_type(
        self, 
        event_name: str, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle specific event types based on LLM analysis"""
        
        handlers = {
            "user_send_text": self.handle_text_message,
            "user_send_group_text": self.handle_group_text_message,
            "user_send_file": self.handle_file_message,
            "user_send_group_file": self.handle_group_file_message,
            "user_send_group_image": self.handle_group_image_message,
            "user_send_group_sticker": self.handle_group_sticker_message,
            "oa_send_group_text": self.handle_oa_group_text_message,
        }

        handler = handlers.get(event_name, self.handle_unknown_event)
        return await handler(payload, analysis)

    async def handle_text_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle individual text messages"""
        sender_id = payload.get("sender", {}).get("id")
        message_text = payload.get("message", {}).get("text", "")
        
        webhook_data = WebhookCreate(
            event_type="user_send_text",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "user_send_text",
            "sender_id": sender_id,
            "message": message_text,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_group_text_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle group text messages"""
        sender_id = payload.get("sender", {}).get("id")
        group_id = payload.get("recipient", {}).get("id")
        message_text = payload.get("message", {}).get("text", "")
        
        webhook_data = WebhookCreate(
            event_type="user_send_group_text",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "user_send_group_text",
            "sender_id": sender_id,
            "group_id": group_id,
            "message": message_text,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_file_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle file messages"""
        sender_id = payload.get("sender", {}).get("id")
        file_info = payload.get("message", {}).get("attachments", [{}])[0].get("payload", {})
        
        webhook_data = WebhookCreate(
            event_type="user_send_file",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "user_send_file",
            "sender_id": sender_id,
            "file_info": file_info,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_group_file_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle group file messages"""
        sender_id = payload.get("sender", {}).get("id")
        group_id = payload.get("recipient", {}).get("id")
        file_info = payload.get("message", {}).get("attachments", [{}])[0].get("payload", {})
        
        logger.info(f"LOGS User send group message")
        webhook_data = WebhookCreate(
            event_type="user_send_group_file",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "user_send_group_file",
            "sender_id": sender_id,
            "group_id": group_id,
            "file_info": file_info,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_group_image_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle group image messages"""
        sender_id = payload.get("sender", {}).get("id")
        group_id = payload.get("recipient", {}).get("id")
        image_info = payload.get("message", {}).get("attachments", [{}])[0].get("payload", {})
        
        webhook_data = WebhookCreate(
            event_type="user_send_group_image",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "user_send_group_image",
            "sender_id": sender_id,
            "group_id": group_id,
            "image_info": image_info,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_group_sticker_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle group sticker messages"""
        sender_id = payload.get("sender", {}).get("id")
        group_id = payload.get("recipient", {}).get("id")
        sticker_info = payload.get("message", {}).get("attachments", [{}])[0].get("payload", {})
        
        webhook_data = WebhookCreate(
            event_type="user_send_group_sticker",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "user_send_group_sticker",
            "sender_id": sender_id,
            "group_id": group_id,
            "sticker_info": sticker_info,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_oa_group_text_message(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle OA group text messages"""
        sender_id = payload.get("sender", {}).get("id")
        group_id = payload.get("recipient", {}).get("id")
        message_text = payload.get("message", {}).get("text", "")
        
        webhook_data = WebhookCreate(
            event_type="oa_send_group_text",
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "oa_send_group_text",
            "sender_id": sender_id,
            "group_id": group_id,
            "message": message_text,
            "analysis": analysis,
            "webhook_id": webhook.id
        }

    async def handle_unknown_event(
        self, 
        payload: Dict[str, Any], 
        analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle unknown event types"""
        webhook_data = WebhookCreate(
            event_type=payload.get("event_name", "unknown"),
            payload=payload
        )
        webhook = self.create_webhook(webhook_data)
        
        return {
            "status": "success",
            "event_type": "unknown",
            "payload": payload,
            "analysis": analysis,
            "webhook_id": webhook.id
        }