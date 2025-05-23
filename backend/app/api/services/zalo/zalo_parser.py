from typing import Any


class ZaloParser:
    @staticmethod
    def parse_message(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        event_type = payload.get("event_name", "unknown")
        parsed_data = {
            "conversation_id": payload.get("message", {}).get("msg_id", ""),
            "sender_id": payload.get("sender", {}).get("id", ""),
            "group_id": payload.get("recipient", {}).get("id"),
            "event_type": event_type,
            "message_text": payload.get("message", {}).get("text"),
            "raw_payload": payload
        }

        # Handle attachments
        attachments = payload.get("message", {}).get("attachments", [])
        if attachments:
            attachment = attachments[0].get("payload", {})
            if "file" in event_type:
                parsed_data.update({
                    "file_url": attachment.get("url"),
                    "file_name": attachment.get("name"),
                    "file_type": attachment.get("type")
                })
            elif "sticker" in event_type:
                parsed_data.update({
                    "sticker_id": attachment.get("id"),
                    "sticker_url": attachment.get("url")
                })
            elif "image" in event_type:
                parsed_data.update({
                    "image_url": attachment.get("url"),
                    "thumbnail_url": attachment.get("thumbnail")
                })

        return event_type, parsed_data
