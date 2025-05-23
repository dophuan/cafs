import json
import logging
from typing import Any

from sqlmodel import Session

from app.api.services.conversation.chat import LLMService, MessageContent
from app.core.config import settings
from app.models.zalo import ZaloConversation, ZaloConversationCreate

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, db: Session, llm_service: LLMService | None = None):
        self.db = db
        self.llm_service = llm_service or LLMService(
            db=db, api_key=settings.OPENAI_API_KEY, engine=settings.OPENAI_ENGINE
        )

    async def analyze_intent(self, message: str) -> dict[str, Any]:
        try:
            # Must mention to active
            system_prompt = """You are an Vietnamese AI assistant helping my company named "Trident Digital" (a.k.a Trident) with inventory management.
            Analyze the message and identify if it's related to:
            - CHECK_STOCK_LEVELS
            - CREATE_RECEIPT
            - UPDATE_STOCK_QUANTITIES
            - ADD_NEW_ITEMS
            - UPDATE_ITEM
            - SEARCH_PRODUCTS
            - NORMAL_CONVERSATION
            You may be called as ["ad", "admin", "ác min", "bot", "Trident"]

            sku will start with "PNT", barcode will start with "BAR"

            Return JSON with identified intent and relevant parameters."""

            messages = [
                MessageContent(role="assistant", content=system_prompt),
                MessageContent(role="user", content=message),
            ]

            response = self.llm_service.query(messages)

            # Clean the response by removing markdown formatting
            cleaned_response = (
                response.replace("```json", "").replace("```", "").strip()
            )
            return json.loads(cleaned_response)
        except Exception as e:
            logger.error(f"Raise error while processing conversation: {str(e)}")
            return {"intent": None, "parameters": {}, "error": str(e)}

    async def store_conversation(self, data: dict[str, Any]) -> ZaloConversation:
        conversation = ZaloConversationCreate(**data)
        db_conversation = ZaloConversation.from_orm(conversation)
        self.db.add(db_conversation)
        self.db.commit()
        self.db.refresh(db_conversation)
        return db_conversation

    async def handle_normal_conversation(self, message: str) -> str:
        """Generate Vietnamese response for normal conversation"""
        system_prompt = """You are a friendly Vietnamese AI assistant for Trident Digital company.
        Keep responses natural, helpful and concise (under 100 words).
        You may be called as "ad", "admin", "ác min", "bot", or "Trident".
        Respond in Vietnamese with a friendly, professional tone."""

        messages = [
            MessageContent(role="assistant", content=system_prompt),
            MessageContent(role="user", content=message),
        ]

        return self.llm_service.query(messages)

    async def process_conversation(
        self, event_type: str, parsed_data: dict[str, Any]
    ) -> dict[str, Any]:
        response_text = None

        if "text" in event_type and parsed_data.get("message_text"):
            # Analyze intent
            intent = await self.analyze_intent(parsed_data["message_text"])
            parsed_data["llm_analysis"] = intent

            # Generate response for normal conversation
            if intent.get("intent") == "NORMAL_CONVERSATION":
                response_text = await self.handle_normal_conversation(
                    parsed_data["message_text"]
                )

        # Store conversation
        conversation = await self.store_conversation(parsed_data)

        return {
            "conversation_id": conversation.id,
            "intent": parsed_data.get("llm_analysis", {}),
            "parsed_data": parsed_data,
            "response_text": response_text,
            "group_id": parsed_data.get("group_id"),
        }
