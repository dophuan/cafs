from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, SessionDep
from app.models.message import ChatRequest, ChatResponse
from app.utils import get_llm_service

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    session: SessionDep,
    current_user: CurrentUser,
    conversation_id: str | None = None,
    conversation_name: str | None = None,
) -> ChatResponse:
    try:
        llm_service = await get_llm_service(session, current_user)

        # Get the user message
        user_message = request.user_message if isinstance(request.user_message, str) else request.user_message[-1].content
        if not user_message:
            raise HTTPException(status_code=400, detail="User message is required")

        # Get the bot's response
        bot_response = llm_service.query(request.user_message)
        if not bot_response:
            raise HTTPException(status_code=500, detail="Failed to get bot response")

        # Save the conversation
        conversation_result = llm_service.create_or_update_conversation(
            conversation_id=conversation_id,
            conversation_name=conversation_name,
            user_message=user_message,
            bot_response=bot_response,
        )

        # Return the bot's response along with conversation info
        return ChatResponse(
            bot_response=bot_response,
            conversation_id=conversation_result.get("conversation_id"),
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error in chat_endpoint: {str(e)}")  # Add this debug line
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/chat/history")
async def chat_history_endpoint(
    session: SessionDep,
    current_user: CurrentUser,
    page: int | None = Query(None, ge=1, description="Page number"),
    page_size: int | None = Query(None, ge=5, le=100, description="Items per page"),
) -> dict[str, Any]:
    try:
        llm_service = await get_llm_service(session, current_user)
        result = llm_service.list_conversations(page=page, page_size=page_size)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/chat/history/{conversation_id}")
async def delete_chat_history_endpoint(
    conversation_id: str, session: SessionDep, current_user: CurrentUser
) -> dict[str, Any]:
    try:
        llm_service = await get_llm_service(session, current_user)
        result = llm_service.delete_conversation(conversation_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/chat/history/{conversation_id}")
async def get_chat_history_endpoint(
    conversation_id: str, session: SessionDep, current_user: CurrentUser
) -> dict[str, list[dict[str, Any]]]:
    try:
        llm_service = await get_llm_service(session, current_user)
        chat_history = llm_service.get_chat_history(conversation_id)
        return {"chat_history": chat_history}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
