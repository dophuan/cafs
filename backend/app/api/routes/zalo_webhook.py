from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.zalo import ZaloService

router = APIRouter()

@router.post("/webhook/zalo/group")
async def zalo_group_webhook(
    request: Request,
    zalo_service: ZaloService = Depends(lambda: ZaloService())
) -> dict[str, Any]:
    body = await request.body()

    zalo_signature = request.headers.get("X-Zalo-Signature")

    if not zalo_signature:
        raise HTTPException(status_code=400, detail="Missing Zalo signature")

    if not zalo_service.verify_webhook_signature(body, zalo_signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    try:
        data: dict[Any, Any] = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_name = data.get("event_name")

    if event_name == "group_message":
        return await zalo_service.process_group_message(data)

    return {"status": "success", "event": event_name}
