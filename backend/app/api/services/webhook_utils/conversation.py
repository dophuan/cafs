import json
import logging
from typing import Dict, Any, Optional
from sqlmodel import Session
from app.core.config import settings
from app.api.services.chat import LLMService, MessageContent
from app.models.zalo import ZaloConversation, ZaloConversationCreate

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConversationService:
    def __init__(self, db: Session, llm_service: Optional[LLMService] = None):
        self.db = db
        self.llm_service = llm_service or LLMService(
            db=db,
            api_key=settings.OPENAI_API_KEY,
            engine=settings.OPENAI_ENGINE
        )

    async def process_conversation(
        self, 
        event_type: str, 
        parsed_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Only analyze text messages for inventory actions
        if "text" in event_type and parsed_data.get("message_text"):
            intent = await self.analyze_intent(parsed_data["message_text"])
            parsed_data["llm_analysis"] = intent
        
        # Store conversation
        conversation = await self.store_conversation(parsed_data)
        
        return {
            "conversation_id": conversation.id,
            "intent": parsed_data.get("llm_analysis", {}),
            "parsed_data": parsed_data
        }

    async def analyze_intent(self, message: str) -> Dict[str, Any]:
        try:
            system_prompt = """You are an Vietnamese AI assistant helping with inventory management.
            Analyze the message and identify if it's related to:
            - Checking stock levels
            - Creating a receipt
            - Updating stock quantities
            - Adding new items
            - Updating item details
            - Searching for products
            
            Return JSON with identified intent and relevant parameters."""

            messages = [
                MessageContent(role="assistant", content=system_prompt),
                MessageContent(role="user", content=message)
            ]
            
            response = self.llm_service.query(messages)
            
            # Clean the response by removing markdown formatting
            cleaned_response = response.replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_response)
        except Exception as e:
            logger.error(f"Raise error while processing conversation: {str(e)}")
            return {
                "intent": None,
                "parameters": {},
                "error": str(e)
            }

    async def store_conversation(self, data: Dict[str, Any]) -> ZaloConversation:
        conversation = ZaloConversationCreate(**data)
        db_conversation = ZaloConversation.from_orm(conversation)
        self.db.add(db_conversation)
        self.db.commit()
        self.db.refresh(db_conversation)
        return db_conversation