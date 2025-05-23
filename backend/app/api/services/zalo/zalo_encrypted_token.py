import json
import os
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, status

from app.core.config import settings


class EncryptedFileTokenStorage:
    def __init__(self):
        try:
            self.key = settings.ENCRYPTION_KEY.encode()
            if not self._is_valid_key(self.key):
                raise ValueError("Invalid encryption key format")

            self.cipher_suite = Fernet(self.key)
            self.file_path = "secure_tokens.enc"
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize encrypted storage: {str(e)}",
            )

    def _is_valid_key(self, key: bytes) -> bool:
        try:
            Fernet(key)
            return True
        except Exception:
            return False

    def store_tokens(
        self, access_token: str, refresh_token: str, expiry: datetime
    ) -> None:
        try:
            data = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expiry": expiry.isoformat(),
            }
            encrypted_data = self.cipher_suite.encrypt(json.dumps(data).encode())

            temp_file = f"{self.file_path}.tmp"
            with open(temp_file, "wb") as file:
                file.write(encrypted_data)

            os.replace(temp_file, self.file_path)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store tokens: {str(e)}",
            )

    def get_tokens(self) -> tuple[str | None, str | None, datetime | None]:
        try:
            if not os.path.exists(self.file_path):
                return None, None, None

            with open(self.file_path, "rb") as file:
                encrypted_data = file.read()

            try:
                decrypted_data = json.loads(self.cipher_suite.decrypt(encrypted_data))
                return (
                    decrypted_data.get("access_token"),
                    decrypted_data.get("refresh_token"),
                    datetime.fromisoformat(decrypted_data["expiry"])
                    if "expiry" in decrypted_data
                    else None,
                )
            except InvalidToken:
                self.clear_token()
                return None, None, None

        except Exception as e:
            print(f"Error retrieving tokens: {str(e)}")
            return None, None, None

    def clear_token(self) -> None:
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
        except Exception as e:
            print(f"Error clearing token: {str(e)}")

    def rotate_key(self, new_key: bytes) -> None:
        if not self._is_valid_key(new_key):
            raise ValueError("Invalid new encryption key format")

        try:
            access_token, refresh_token, expiry = self.get_tokens()
            if access_token and refresh_token and expiry:
                new_cipher = Fernet(new_key)
                self.key = new_key
                self.cipher_suite = new_cipher
                self.store_tokens(access_token, refresh_token, expiry)

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to rotate encryption key: {str(e)}",
            )
