from typing import Any

from fastapi import APIRouter, Depends

from app.api.services.zalo.zalo_interaction import ZaloInteractionService
from app.models.message import (
    ConversationRequest,
    ConversationWithInventoryRequest,
    GroupMessageRequest,
)

router = APIRouter(prefix="/zalo", tags=["zalo"])

# Dependency to get service instance
def get_zalo_service():
    return ZaloInteractionService()

@router.post("/group/message", response_model=dict[str, Any])
async def send_group_message(
    request: GroupMessageRequest,
    service: ZaloInteractionService = Depends(get_zalo_service)
):
    """
    Send a message to a Zalo group
    """
    return await service.send_group_message(
        group_id=request.group_id,
        text=request.text
    )

@router.post("/conversation/normal", response_model=dict[str, Any])
async def handle_normal_conversation(
    conversation: ConversationRequest,
    service: ZaloInteractionService = Depends(get_zalo_service)
):
    """
    Handle normal conversation and send response
    """
    conversation_result = {
        "group_id": conversation.group_id,
        "response_text": conversation.response_text
    }
    return await service.handle_normal_conversation(conversation_result)

@router.post("/conversation/inventory", response_model=dict[str, Any])
async def handle_inventory_conversation(
    request: ConversationWithInventoryRequest,
    service: ZaloInteractionService = Depends(get_zalo_service)
):
    """
    Handle inventory-related conversation and send response
    """
    conversation_result = {
        "group_id": request.conversation.group_id,
        "response_text": request.conversation.response_text
    }

    inventory_action = {
        "message": request.inventory_action.message,
        "action": request.inventory_action.action
    }

    return await service.handle_inventory_response(
        conversation_result=conversation_result,
        inventory_action=inventory_action
    )
