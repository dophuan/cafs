import json
import requests
from fastapi import HTTPException, status
from typing import Dict, Any
from app.core.config import settings
from datetime import datetime, timedelta

class ZaloInteractionService:
    def __init__(self):
        self.app_secret_key = settings.ZALO_APP_SECRET_KEY
        self.refresh_token = settings.ZALO_REFRESH_TOKEN
        self._access_token = None
        self._token_expiry = None

    def _get_access_token(self) -> str:
        """
        Get a new access token using the refresh token and store it with expiration time
        """
        try:
            # Check if we have a valid token
            if self._access_token and self._token_expiry and datetime.now() < self._token_expiry:
                return self._access_token

            url = "https://oauth.zaloapp.com/v4/oa/access_token"
            
            payload = {
                "refresh_token": self.refresh_token,
                "app_id": settings.ZALO_APP_ID,
                "grant_type": "refresh_token"
            }

            print(f"Payload {json.dumps(payload)}")
            
            headers = {
                "secret_key": self.app_secret_key,
                "Content-Type": "application/x-www-form-urlencoded"
            }

            print(f"Header {json.dumps(headers)}")
            
            response = requests.post(
                url,
                headers=headers,
                data=payload,
                timeout=30
            )
            print(f"Response {json.dumps(response)}")
            response.raise_for_status()
            result = response.json()
            
            if "access_token" not in result:
                raise ValueError("No access token in response")
                
            self._access_token = result["access_token"]
            # Set token expiry to 24 hours from now (to be safe, slightly less than the 25-hour limit)
            self._token_expiry = datetime.now() + timedelta(hours=24)
            return self._access_token

        except requests.RequestException as e:
            # Clear token data on error
            self._access_token = None
            self._token_expiry = None
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get Zalo access token: {str(e)}"
            )
            
        except Exception as e:
            # Clear token data on error
            self._access_token = None
            self._token_expiry = None
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error getting Zalo access token: {str(e)}"
            )

    async def send_group_message(self, group_id: str, text: str) -> Dict[str, Any]:
        """
        Send a text message to a Zalo group using the Zalo Open API
        """
        try:
            # Get cached token or fetch new one if expired
            access_token = self._get_access_token()

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
            
            # If token expired, clear cached token and retry once
            if response.status_code == 401:
                self._access_token = None
                self._token_expiry = None
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

        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to send Zalo group message: {str(e)}"
            )
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error sending Zalo group message: {str(e)}"
            )
        
    async def handle_normal_conversation(self, conversation_result: Dict[str, Any]) -> Dict[str, Any]:
        """Handle normal conversation response and send message"""
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
        """Handle inventory action responses and send to Zalo group"""
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