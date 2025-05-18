import uuid
from datetime import datetime
from typing import Any, Union, List, Dict

import requests
from fastapi import HTTPException, status
from pydantic import BaseModel, validator
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    delete,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Session
from sqlmodel import select as sqlmodel_select
from openai import OpenAI

from app.models.message import LLMConversation

class MessageContent(BaseModel):
    role: str
    content: str

    @validator("role")
    def validate_role(cls, v: str) -> str:
        if v not in ["user", "assistant"]:
            raise ValueError('Role must be either "user" or "assistant"')
        return v

class ChatRequest(BaseModel):
    user_message: Union[str, List[MessageContent]]

class ChatResponse(BaseModel):
    bot_response: str
    conversation_id: str | None = None

class ConversationRequest(BaseModel):
    conversation_id: str | None = None
    conversation_name: str | None = None
    user_message: str
    bot_response: str

class LLMService:
    def __init__(
        self,
        db: Session | None = None,
        user_id: str | None = None,
        api_key: str | None = None,
        engine: str | None = None,
        local_endpoint: str | None = None,
    ):
        self.db = db
        self.user_id = user_id
        self.api_key = api_key
        self.engine = engine
        self.local_endpoint = local_endpoint

    def query(self, prompt: Union[str, List[MessageContent]]) -> str:
        try:            
            messages = []
            if isinstance(prompt, str):
                messages = [{"role": "user", "content": prompt}]
            else:
                messages = [{"role": msg.role, "content": msg.content} for msg in prompt]

            # First try OpenAI if API key is available
            if self.api_key:
                try:
                    client = OpenAI(api_key=self.api_key)
                    response = client.chat.completions.create(
                        model=self.engine or "gpt-3.5-turbo",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=2000
                    )
                    return response.choices[0].message.content.strip()
                except Exception as e:
                    print(f"OpenAI API error: {str(e)}")
                    # If OpenAI fails and local endpoint is available, fall back to local
                    if not self.local_endpoint:
                        raise

            # Fall back to local endpoint if OpenAI is not configured or failed
            if self.local_endpoint:
                headers = {
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": "mistral-7b-instruct-v0.2",
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2000,
                    "stream": False
                }

                response = requests.post(
                    f"{self.local_endpoint}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                response.raise_for_status()
                json_response = response.json()
                
                if "choices" in json_response and len(json_response["choices"]) > 0:
                    return str(json_response["choices"][0]["message"]["content"]).strip()
                return ""

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No LLM service available"
            )
                    
        except requests.RequestException as e:
            print(f"Error connecting to LLM: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Chat API request failed: {str(e)}"
            )

    # Rest of the methods remain unchanged
    def list_conversations(
        self, page: int | None = None, page_size: int | None = None
    ) -> dict[str, Any]:
        try:
            if not self.db or not self.user_id:
                return {
                    "conversations": [],
                    "total": 0,
                    "current_page": page or 1,
                    "is_last_page": True,
                }

            page = page or 1
            page_size = page_size or 10

            user_id_param = (
                uuid.UUID(self.user_id)
                if isinstance(self.user_id, str)
                else self.user_id
            )

            count_query = sqlmodel_select(func.count()).select_from(LLMConversation).where(
                LLMConversation.user_id == user_id_param
            )

            total_count = self.db.execute(count_query).scalar() or 0

            if total_count == 0:
                return {
                    "conversations": [],
                    "total": 0,
                    "current_page": page,
                    "is_last_page": True,
                }

            offset = (page - 1) * page_size
            is_last_page = (offset + page_size) >= total_count

            statement = (
                sqlmodel_select(
                    LLMConversation.id,
                    LLMConversation.title,
                    LLMConversation.created_at,
                    LLMConversation.updated_at,
                )
                .where(LLMConversation.user_id == user_id_param)
                .order_by(LLMConversation.updated_at.desc())
                .limit(page_size)
                .offset(offset)
            )
            query_result = self.db.exec(statement).all()

            return {
                "conversations": [
                    {
                        "id": str(row[0]) if isinstance(row[0], uuid.UUID) else row[0],
                        "title": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                    }
                    for row in query_result
                ],
                "total": total_count,
                "current_page": page,
                "is_last_page": is_last_page,
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch conversations: {str(e)}",
            )

    def delete_conversation(self, conversation_id: str) -> dict[str, str]:
        if not self.db or not self.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database session or user ID not available",
            )
        try:
            metadata = MetaData()
            conversations = Table(
                "llm_conversations",
                metadata,
                Column("id", UUID),
                Column("user_id", UUID),
            )

            user_id_param = (
                uuid.UUID(self.user_id)
                if isinstance(self.user_id, str)
                else self.user_id
            )
            conversation_id_param = (
                uuid.UUID(conversation_id)
                if isinstance(conversation_id, str)
                else conversation_id
            )

            delete_stmt = delete(conversations).where(
                (conversations.c.id == conversation_id_param)
                & (conversations.c.user_id == user_id_param)
            )

            result = self.db.execute(delete_stmt)

            found = False
            if hasattr(result, "rowcount"):
                found = result.rowcount > 0

            if not found:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conversation with ID {conversation_id} not found or you don't have permission to delete it",
                )

            self.db.commit()
            return {
                "status": "success",
                "message": f"Conversation {conversation_id} deleted successfully",
            }

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete conversation: {str(e)}",
            )

    def get_chat_history(self, conversation_id: str) -> List[Dict[str, str]]:
        if not self.db or not self.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database session or user ID not available",
            )

        try:
            user_id_param = (
                uuid.UUID(self.user_id)
                if isinstance(self.user_id, str)
                else self.user_id
            )
            conversation_id_param = (
                uuid.UUID(conversation_id)
                if isinstance(conversation_id, str)
                else conversation_id
            )

            from sqlmodel import and_

            query_result = (
                self.db.query(LLMConversation)
                .filter(
                    and_(
                        LLMConversation.id == conversation_id_param,
                        LLMConversation.user_id == user_id_param,
                    )
                )
                .first()
            )

            if not query_result:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conversation with ID {conversation_id} not found or doesn't belong to you",
                )

            return query_result.messages or []

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch chat history: {str(e)}",
            )

    def create_or_update_conversation(
        self,
        conversation_id: str | None = None,
        conversation_name: str | None = None,
        user_message: str | None = None,
        bot_response: str | None = None,
    ) -> dict[str, Any]:
        if not self.db or not self.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Database session or user ID not available",
            )

        try:
            current_time = datetime.now()

            if not user_message or not bot_response:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User message and bot response are required",
                )

            new_messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": bot_response},
            ]

            if conversation_id:
                conversation_id_uuid = (
                    uuid.UUID(conversation_id)
                    if isinstance(conversation_id, str)
                    else conversation_id
                )
                user_id_uuid = (
                    uuid.UUID(self.user_id)
                    if isinstance(self.user_id, str)
                    else self.user_id
                )

                from sqlmodel import and_

                existing_conversation = (
                    self.db.query(LLMConversation)
                    .filter(
                        and_(
                            LLMConversation.id == conversation_id_uuid,
                            LLMConversation.user_id == user_id_uuid,
                        )
                    )
                    .first()
                )

                if not existing_conversation:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Conversation with ID {conversation_id} not found or doesn't belong to you",
                    )

                existing_messages = existing_conversation.messages or []
                existing_conversation.messages = existing_messages + new_messages
                existing_conversation.updated_at = current_time

                self.db.commit()

                return {
                    "status": "success",
                    "message": "Conversation updated successfully",
                    "conversation_id": str(conversation_id_uuid),
                }
            else:
                new_id = uuid.uuid4()
                name = (
                    conversation_name
                    or f"Chat {current_time.strftime('%Y-%m-%d %H:%M')}"
                )

                user_id_uuid = (
                    uuid.UUID(self.user_id)
                    if isinstance(self.user_id, str)
                    else self.user_id
                )

                new_conversation = LLMConversation(
                    id=new_id,
                    user_id=user_id_uuid,
                    title=name,
                    created_at=current_time,
                    updated_at=current_time,
                    file_urls=[],
                    messages=new_messages,
                    model_name=None,
                    total_tokens=None,
                    meta_data={},
                )

                self.db.add(new_conversation)
                self.db.commit()

                return {
                    "status": "success",
                    "message": f"Conversation '{name}' created successfully",
                    "conversation_id": str(new_id),
                }

        except HTTPException:
            raise
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create/update conversation: {str(e)}",
            )
        
    async def parse_product_query(self, user_message: str) -> Dict[str, Any]:
        """
        Use LLM to parse user's natural language query about paint products into structured search parameters
        based on all available columns in the item table
        """
        system_prompt = """You are an AI assistant for Trident Digital, a major paint manufacturing company. Your task is to analyze customer queries about paint products and extract search parameters based on our database structure.
        
        Available fields for search:
        - title: Product name/title
        - description: Product description
        - sku: Product SKU (format: PNT-XXXX)
        - category: Paint category (Sơn Nội Thất, Sơn Ngoại Thất, Sơn Lót, Sơn Đặc Biệt)
        - price: Product price in VND
        - quantity: Current stock quantity
        - dimensions: JSON object containing height, width, depth, weight, unit
        - color_code: Color code or name
        - specifications: JSON object containing:
            - finish: Surface finish (Mờ, Mịn, Bóng Mờ, Bóng)
            - coverage: Coverage area
            - dry_time: Drying time
            - base_type: Base type (Gốc Nước, Gốc Dầu)
        - tags: Array of product tags
        - status: Product status (active, out_of_stock, discontinued)
        - unit: Unit of measurement (Lít)
        - barcode: Product barcode
        - supplier_id: Supplier identifier
        - reorder_point: Minimum stock level before reorder
        - max_stock: Maximum stock level

        Return a JSON object containing any mentioned search parameters. Only include fields that are relevant to the query.
        
        Example output:
        {
            "search_parameters": {
                "category": "Sơn Ngoại Thất",
                "color_code": "kem",
                "price": {"operator": "<", "value": 400000},
                "specifications": {"finish": "bóng"},
                "status": "active"
            },
            "sort_parameters": {
                "field": "price",
                "order": "asc"
            }
        }
        """

        user_prompt = f"Parse this query and extract relevant search parameters: {user_message}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.query(messages)
            
            try:
                import json
                parsed_result = json.loads(response)
                
                # Validate and clean the parsed parameters
                if not isinstance(parsed_result, dict):
                    raise ValueError("Invalid response format")

                return {
                    "status": "success",
                    "parameters": parsed_result
                }

            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "message": f"Failed to parse LLM response as JSON: {str(e)}",
                    "parameters": {"search_term": user_message}
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error parsing product query: {str(e)}",
                "parameters": {"search_term": user_message}
            }