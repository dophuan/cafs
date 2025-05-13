from typing import List, Any
from app.api.services.webhook import WebhookService
from fastapi import APIRouter, Depends, HTTPException, Request, Header

from app.models.webhook import WebhookRead
from app.api import deps

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/", response_model=WebhookRead)
async def create_webhook(
    *,
    request: Request,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),  # Updated import
    x_webhook_signature: str = Header(None)
) -> Any:
    """
    Receive webhook events
    """
    payload = await request.body()
    
    if x_webhook_signature and not webhook_service.verify_signature(
        payload, x_webhook_signature
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )
    
    payload_json = await request.json()
    webhook_data = webhook_service.process_webhook_payload(payload_json)
    
    return webhook_service.create_webhook(webhook_data)

@router.get("/", response_model=List[WebhookRead])
def read_webhooks(
    skip: int = 0,
    limit: int = 100,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),  # Updated import
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve webhooks with pagination
    """
    return webhook_service.get_webhooks(skip=skip, limit=limit)

@router.get("/event/{event_type}", response_model=List[WebhookRead])
def read_webhooks_by_event(
    event_type: str,
    skip: int = 0,
    limit: int = 100,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),  # Updated import
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve webhooks filtered by event type
    """
    return webhook_service.get_webhooks_by_event_type(
        event_type=event_type,
        skip=skip,
        limit=limit
    )

@router.get("/{webhook_id}", response_model=WebhookRead)
def read_webhook(
    webhook_id: int,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),  # Updated import
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve specific webhook by ID
    """
    webhook = webhook_service.get_webhook_by_id(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook