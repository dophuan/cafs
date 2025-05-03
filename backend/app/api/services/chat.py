import json
import uuid
from datetime import datetime
from typing import Any

import openai
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

from app.models.message import LLMConversation


class ChatRequest(BaseModel):
    user_message: str


class ChatResponse(BaseModel):
    bot_response: str
    conversation_id: str | None = None


class MessageContent(BaseModel):
    role: str
    content: str

    @validator("role")
    def validate_role(cls, v: str) -> str:
        if v not in ["user", "assistant"]:
            raise ValueError('Role must be either "user" or "assistant"')
        return v


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

    def query(self, prompt: str) -> str:
        if self.local_endpoint:
            errors: list[str] = []
            try:
                response = requests.post(
                    f"{self.local_endpoint}/v1/completions",
                    json={"prompt": prompt, "max_tokens": 150, "temperature": 0.7},
                )
                response.raise_for_status()
                json_response = response.json()
                if "choices" in json_response and len(json_response["choices"]) > 0:
                    return str(json_response["choices"][0]["text"]).strip()
                return ""
            except requests.RequestException as e:
                errors.append(f"Completions endpoint failed: {str(e)}")

            try:
                response = requests.post(
                    self.local_endpoint,
                    json={"prompt": prompt, "max_tokens": 150, "temperature": 0.7},
                )
                response.raise_for_status()
                result = response.json()

                if "response" in result:
                    return str(result["response"]).strip()
                elif "output" in result:
                    return str(result["output"]).strip()
                elif "generated_text" in result:
                    return str(result["generated_text"]).strip()
                elif "choices" in result and len(result["choices"]) > 0:
                    choice = result["choices"][0]
                    if isinstance(choice, dict) and "text" in choice:
                        return str(choice["text"]).strip()
                elif isinstance(result, str):
                    return result.strip()

                return f"Received response but couldn't parse it: {json.dumps(result)}"
            except requests.RequestException as e:
                errors.append(f"Root endpoint failed: {str(e)}")

            error_msg = "; ".join(errors)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"All local LLM attempts failed: {error_msg}",
            )
        else:
            if not self.api_key:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="API key is required",
                )

            openai.api_key = self.api_key
            try:
                engine_name = self.engine if self.engine else "text-davinci-003"

                completion = openai.completions.create(
                    model=engine_name, prompt=prompt, max_tokens=150, temperature=0.7
                )

                if hasattr(completion, "choices") and len(completion.choices) > 0:
                    if hasattr(completion.choices[0], "text"):
                        return str(completion.choices[0].text).strip()

                return ""
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"LLM interaction failed: {str(e)}",
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

            # Get the actual column names directly from the model to ensure alignment
            user_id_param = (
                uuid.UUID(self.user_id)
                if isinstance(self.user_id, str)
                else self.user_id
            )

            # Use explicit column references from LLMConversation model
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

            # Use the SQLModel query pattern instead of raw SQL
            statement = (
                sqlmodel_select(
                    LLMConversation.id,
                    LLMConversation.title,
                    LLMConversation.created_at,
                    LLMConversation.updated_at,
                )
                .where(LLMConversation.user_id == user_id_param)
                .order_by(LLMConversation.updated_at.desc())  # Fixed datetime.desc() error
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

            # Use SQLModel's query approach
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

            messages = query_result.messages or []

            chat_history = []
            for i in range(0, len(messages), 2):
                if i + 1 < len(messages):
                    chat_history.append(
                        {
                            "user": messages[i].get("content", ""),
                            "bot": messages[i + 1].get("content", ""),
                        }
                    )
                else:
                    chat_history.append(
                        {"user": messages[i].get("content", ""), "bot": ""}
                    )

            return chat_history

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

                # Use SQLModel's query approach
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
