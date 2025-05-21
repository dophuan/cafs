from typing import List, Any
from app.api.services.webhook.webhook import WebhookService
from fastapi import APIRouter, Depends, HTTPException, Request, Header, Response
from fastapi.responses import JSONResponse

from app.models.webhook import WebhookRead
from app.api import deps

# Create two separate routers
webhook_public = APIRouter(prefix="/webhooks", tags=["webhooks"])
webhook_private = APIRouter(
    prefix="/webhook-history",
    tags=["webhooks"],
    dependencies=[Depends(deps.get_current_active_superuser)]
)

@webhook_public.post("/")
async def create_webhook(
    *,
    request: Request,
    webhook_service: WebhookService = Depends(deps.get_webhook_service),
    x_webhook_signature: str = Header(None)
) -> Response:
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
    
    try:
        payload_json = await request.json()
        
        # First store the raw webhook data
        webhook_data = webhook_service.process_webhook_payload(payload_json)
        webhook = await webhook_service.create_webhook(webhook_data)
        
        # Then process the Zalo event and handle any inventory actions
        result = await webhook_service.process_webhook(payload_json)
        
        return JSONResponse(
            content={
                "status": "success",
                "webhook_id": webhook.id,
                "result": result
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error create processing webhook: {str(e)}"
        )

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