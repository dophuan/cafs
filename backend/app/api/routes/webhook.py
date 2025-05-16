from typing import List, Any
from app.api.services.webhook import WebhookService
from fastapi import APIRouter, Depends, HTTPException, Request, Header

from app.models.webhook import WebhookRead
from app.api import deps

# Create two separate routers
webhook_public = APIRouter(prefix="/webhooks", tags=["webhooks"])  # Only for POST
webhook_private = APIRouter(
    prefix="/webhook-history",  # Different path for all GET operations
    tags=["webhooks"],
    dependencies=[Depends(deps.get_current_active_superuser)]
)

# Public POST endpoint - /webhooks is exclusively for receiving webhooks
@webhook_public.post("/", response_model=WebhookRead)
async def create_webhook(
    *,
    request: Request,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),
    x_webhook_signature: str = Header(None)
) -> Any:
    """
    Receive webhook events - public endpoint
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

# All GET operations moved to /webhook-history
@webhook_private.get("/", response_model=List[WebhookRead])
def read_webhooks(
    skip: int = 0,
    limit: int = 100,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),
) -> Any:
    """
    Retrieve webhooks with pagination
    """
    return webhook_service.get_webhooks(skip=skip, limit=limit)

@webhook_private.get("/event/{event_type}", response_model=List[WebhookRead])
def read_webhooks_by_event(
    event_type: str,
    skip: int = 0,
    limit: int = 100,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),
) -> Any:
    """
    Retrieve webhooks filtered by event type
    """
    return webhook_service.get_webhooks_by_event_type(
        event_type=event_type,
        skip=skip,
        limit=limit
    )

@webhook_private.get("/{webhook_id}", response_model=WebhookRead)
def read_webhook(
    webhook_id: int,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),
) -> Any:
    """
    Retrieve specific webhook by ID
    """
    webhook = webhook_service.get_webhook_by_id(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook

# Export both routers
router = APIRouter()
router.include_router(webhook_public)
router.include_router(webhook_private)