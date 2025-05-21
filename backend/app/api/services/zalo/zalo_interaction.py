from datetime import datetime, timedelta
import json
import requests
from fastapi import HTTPException, status
from typing import Dict, Any
from app.core.config import settings
from app.api.services.zalo.zalo_encrypted_token import EncryptedFileTokenStorage
class ZaloInteractionService:
    def __init__(self):
        self.app_secret_key = settings.ZALO_APP_SECRET_KEY
        self.token_storage = EncryptedFileTokenStorage()

    def _get_access_token(self) -> str:
        try:
            # Check if we have a valid stored token first
            access_token, refresh_token, token_expiry = self.token_storage.get_tokens()
            
            # If we have a valid token that's not expired, return it immediately
            if access_token and token_expiry and datetime.now() < token_expiry:
                return access_token

            # Only get new token if stored one is expired or missing
            refresh_token = refresh_token or settings.ZALO_REFRESH_TOKEN
            
            url = "https://oauth.zaloapp.com/v4/oa/access_token"
            
            payload = {
                "refresh_token": refresh_token,
                "app_id": str(settings.ZALO_APP_ID),
                "grant_type": "refresh_token"
            }

            headers = {
                "secret_key": self.app_secret_key,
                "Content-Type": "application/x-www-form-urlencoded"
            }

            response = requests.post(
                url,
                headers=headers,
                data=payload,
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            if "access_token" not in result:
                raise ValueError(f"No access token in response. Response content: {result}")

            # Store new tokens with 24 hour expiry
            access_token = result["access_token"]
            new_refresh_token = result.get("refresh_token")
            
            if new_refresh_token:
                expiry = datetime.now() + timedelta(hours=24)
                self.token_storage.store_tokens(access_token, new_refresh_token, expiry)
            else:
                raise ValueError("No refresh token in response")
                
            return access_token

        except Exception as e:
            self.token_storage.clear_token()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get Zalo access token: {str(e)}"
            )

    async def send_group_message(self, group_id: str, text: str) -> Dict[str, Any]:
        try:
            access_token = self._get_access_token()  # This will use cached token if valid
            url = "https://openapi.zalo.me/v3.0/oa/group/message"
            
            headers = {
                "access_token": access_token,
                "Content-Type": "application/json"
            }
            
            payload = {
                "recipient": {
                    "group_id": group_id
                },
                "message": {
                    "text": text
                }
            }
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            # If token expired, clear it and try once with new token
            if response.status_code == 401:
                self.token_storage.clear_token()
                access_token = self._get_access_token()
                headers["access_token"] = access_token
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30
                )

            response.raise_for_status()
            return response.json()

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send Zalo group message: {str(e)}"
            )
        
    async def handle_normal_conversation(self, conversation_result: Dict[str, Any]) -> Dict[str, Any]:
        if not conversation_result.get("response_text") or not conversation_result.get("group_id"):
            return {"response_sent": False}
            
        group_id = conversation_result["group_id"]
        resp_text = conversation_result["response_text"]

        await self.send_group_message(
            group_id=group_id,
            text=resp_text
        )
        
        return {
            "response_sent": True,
            "response_text": resp_text
        }
    
    async def handle_inventory_response(
        self, 
        conversation_result: Dict[str, Any],
        inventory_action: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            if not conversation_result.get("group_id"):
                return {"response_sent": False, "error": "No group ID provided"}

            group_id = conversation_result["group_id"]
            message = inventory_action.get("message", "Không có thông tin phản hồi")

            await self.send_group_message(
                group_id=group_id,
                text=message
            )

            return {
                "response_sent": True,
                "response_text": message,
                "action": inventory_action.get("action")
            }

        except Exception as e:
            return {
                "response_sent": False,
                "error": str(e)
            }