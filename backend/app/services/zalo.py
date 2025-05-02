import hashlib
import hmac
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings


class ZaloService:
    def __init__(self) -> None:
        self.app_id = settings.ZALO_APP_ID
        self.app_secret = settings.ZALO_APP_SECRET
        self.access_token = settings.ZALO_ACCESS_TOKEN
        self.webhook_secret = settings.ZALO_WEBHOOK_SECRET
        self.callback_url = settings.ZALO_CALLBACK_URL

    def generate_app_secret_proof(self) -> str:
        """Generate app_secret_proof for Zalo API calls"""
        return hmac.new(
            self.app_secret.encode('utf-8'),
            self.access_token.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def verify_webhook_signature(self, data: bytes, signature: str) -> bool:
        """Verify incoming webhook signature"""
        computed_signature = hmac.new(
            self.webhook_secret.encode(),
            data,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(computed_signature, signature)

    async def process_group_message(self, data: dict[Any, Any]) -> dict[str, Any]:
        """Process group message events"""
        try:
            group_data = data.get("group", {})
            sender_data = data.get("sender", {})
            message_data = data.get("message", {})

            processed_message = {
                "group_id": group_data.get("group_id"),
                "sender_id": sender_data.get("id"),
                "sender_name": sender_data.get("display_name"),
                "msg_id": message_data.get("msg_id"),
                "timestamp": datetime.now().isoformat(),
                "message_type": self._determine_message_type(message_data),
                "content": self._extract_message_content(message_data)
            }

            # Log the processed message
            # logger.info(f"Processed group message: {json.dumps(processed_message)}")

            return processed_message

        except Exception:
            # logger.error(f"Error processing group message: {str(e)}")
            raise

    def _determine_message_type(self, message_data: dict[Any, Any]) -> str:
        """Determine the type of message received"""
        if "text" in message_data:
            return "text"
        elif "attachments" in message_data:
            attachment = message_data["attachments"][0]
            return str(attachment.get("type", "unknown"))
        return "unknown"

    def _extract_message_content(self, message_data: dict[Any, Any]) -> dict[str, Any]:
        """Extract content from message based on type"""
        if "text" in message_data:
            return {"text": message_data["text"]}

        if "attachments" in message_data:
            attachment = message_data["attachments"][0]
            attachment_type = attachment.get("type")
            payload = attachment.get("payload", {})

            if attachment_type == "image":
                return {
                    "type": "image",
                    "url": payload.get("url"),
                    "thumbnail": payload.get("thumbnail")
                }
            elif attachment_type == "file":
                return {
                    "type": "file",
                    "url": payload.get("url"),
                    "name": payload.get("name"),
                    "size": payload.get("size")
                }

        return {"type": "unknown"}

    async def send_message_to_group(
        self,
        group_id: str,
        message: str,
        client: Any | None = None
    ) -> dict[str, Any]:
        """Send message to a group"""
        # Note: Implementation depends on your HTTP client
        # This is a placeholder for the actual implementation
        return {"status": "success", "group_id": group_id, "message": message}

    async def get_oauth_url(self, state: str) -> str:
        """Generate OAuth URL for authorization"""
        return (
            "https://oauth.zaloapp.com/v4/permission"
            f"?app_id={self.app_id}"
            f"&redirect_uri={self.callback_url}"
            f"&state={state}"
        )

    async def get_access_token(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access token"""
        url = "https://oauth.zaloapp.com/v4/access_token"

        params = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
            "code": code,
            "grant_type": "authorization_code"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params)
            data = response.json()

            if "access_token" not in data:
                raise ValueError(f"Failed to get access token: {data}")

            return dict(data)

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh access token using refresh token"""
        url = "https://oauth.zaloapp.com/v4/access_token"

        params = {
            "app_id": self.app_id,
            "app_secret": self.app_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params)
            data = response.json()

            if "access_token" not in data:
                raise ValueError(f"Failed to refresh token: {data}")

            return dict(data)

    async def get_user_profile(self, access_token: str) -> dict[str, Any]:
        """Get user profile information"""
        url = "https://graph.zalo.me/v2.0/me"
        headers = {
            "access_token": access_token,
            "app_secret_proof": self.generate_app_secret_proof()
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            return dict(response.json())
