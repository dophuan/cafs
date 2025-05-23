import json
import logging
import uuid
from datetime import datetime
from typing import Any

import requests
from fastapi import HTTPException, status
from openai import OpenAI
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    and_,
    delete,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Session
from sqlmodel import select as sqlmodel_select

from app.models.message import LLMConversation, MessageContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

    def query(self, prompt: str | list[MessageContent]) -> str:
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
                    logger.info(f"OpenAI API error: {str(e)}")
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
            logger.info(f"Error connecting to LLM: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Chat API request failed: {str(e)}"
            )

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

    def get_chat_history(self, conversation_id: str) -> list[dict[str, str]]:
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

    async def parse_product_query(self, user_message: str) -> dict[str, Any]:
        """
        Use LLM to parse Vietnamese user queries and convert them into search parameters
        that can be used with SearchUtils
        """
        system_prompt = """You are an AI assistant for Trident Digital, a major paint manufacturing company. Your task is to analyze Vietnamese customer queries about paint products and extract search parameters based on our database structure.

    IMPORTANT: You must ONLY return a valid JSON object with the exact structure shown in the example. DO NOT include any other text or explanation.

    Available fields for search:
    - title: Tên sản phẩm
    - description: Mô tả sản phẩm
    - sku: Mã sản phẩm (định dạng: PNT-XXXX)
    - category: Loại sơn (Sơn Nội Thất, Sơn Ngoại Thất, Sơn Lót, Sơn Đặc Biệt)
    - price: Giá (VNĐ)
    - quantity: Số lượng tồn kho
    - color_code: Mã màu hoặc tên màu
    - specifications: Thông số kỹ thuật:
        - finish: Bề mặt (Mờ, Mịn, Bóng Mờ, Bóng)
        - coverage: Độ phủ
        - dry_time: Thời gian khô
        - base_type: Loại gốc (Gốc Nước, Gốc Dầu)
    - tags: Từ khóa sản phẩm
    - status: Trạng thái (đang_bán, hết_hàng, ngừng_kinh_doanh)
    - unit: Đơn vị tính (Lít)

    When parsing price values:
    - Convert word numbers to numeric values (e.g., "bốn trăm nghìn" -> 400000, 400k -> 400000, 4tr -> 4.000.000)
    - Handle price ranges (e.g., "từ 200 đến 500k" -> {"min": 200000, "max": 500000})
    - Handle comparisons (e.g., "dưới 400k" -> {"operator": "<", "value": 400000})

    Example Vietnamese query: "tìm sơn ngoại thất màu kem giá dưới 400 nghìn bề mặt bóng và gốc nước"
    Example output:
    {
        "search_parameters": {
            "category": "Sơn Ngoại Thất",
            "color_code": "kem",
            "price": {"operator": "<", "value": 400000},
            "specifications": {
                "finish": "bóng",
                "base_type": "Gốc Nước"
            }
        },
        "sort_parameters": {
            "field": "price",
            "order": "asc"
        }
    }

    REMEMBER: Return ONLY the JSON object, no other text."""

        user_prompt = f"""Parse this Vietnamese query into the exact JSON format shown in the example. Query: "{user_message}"

    IMPORTANT: Return ONLY the JSON object, no other text or explanation."""

        messages = [
            MessageContent(role="assistant", content=system_prompt),
            MessageContent(role="user", content=user_prompt)
        ]

        try:
            response = self.query(messages)

            if not response or not response.strip():
                return {
                    "status": "error",
                    "message": "Empty response from LLM",
                    "parameters": {"title": user_message}
                }

            try:
                cleaned_response = response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()

                parsed_result = json.loads(cleaned_response)

                if not isinstance(parsed_result, dict):
                    raise ValueError("Invalid response format")

                # Extract search parameters
                search_params = parsed_result.get("search_parameters", {})

                # Transform the parameters if needed to match SearchUtils expectations
                transformed_params = search_params.copy()

                # Special handling for specifications
                if "specifications" in transformed_params:
                    specs = transformed_params["specifications"]
                    # Ensure all spec values are strings
                    transformed_params["specifications"] = {
                        k: str(v) for k, v in specs.items()
                    }

                # Handle price formatting
                if "price" in transformed_params:
                    price_param = transformed_params["price"]
                    if isinstance(price_param, dict):
                        # Keep the existing format as SearchUtils can handle it
                        pass
                    else:
                        # Convert simple price to exact match format
                        transformed_params["price"] = {
                            "operator": "=",
                            "value": float(price_param)
                        }

                return {
                    "status": "success",
                    "parameters": transformed_params,
                    "sort": parsed_result.get("sort_parameters")
                }

            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "message": f"Failed to parse LLM response as JSON: {str(e)}",
                    "parameters": {"title": user_message}
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error parsing product query: {str(e)}",
                "parameters": {"title": user_message}
            }
