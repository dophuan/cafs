import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.services.zalo import ZaloService

router = APIRouter()

def generate_state_token() -> str:
    return secrets.token_urlsafe(32)

@router.get("/login")
async def zalo_login(
    request: Request,
    zalo_service: ZaloService = Depends(lambda: ZaloService())
) -> RedirectResponse:
    state = generate_state_token()

    request.session["oauth_state"] = state

    oauth_url = await zalo_service.get_oauth_url(state)

    return RedirectResponse(oauth_url)

@router.get("/callback")
async def zalo_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    zalo_service: ZaloService = Depends(lambda: ZaloService())
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")

    stored_state = request.session.get("oauth_state")
    if not state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid state token")

    try:
        token_data = await zalo_service.get_access_token(code)

        user_profile = await zalo_service.get_user_profile(token_data["access_token"])

        request.session["access_token"] = token_data["access_token"]
        request.session["refresh_token"] = token_data.get("refresh_token")
        request.session["user_profile"] = user_profile

        return RedirectResponse(settings.ZALO_HOME_URL)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
