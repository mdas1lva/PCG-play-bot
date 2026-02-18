from base64 import urlsafe_b64decode
from datetime import datetime
from json import loads


class PokeJwt:
    """

    A class to deal with PCG JWT extracted from Twitch.
    Contains raw JWT string and expiration date.
    """

    def __init__(self, encoded_jwt):
        if encoded_jwt.startswith("v4.local"):
            raise ValueError("Invalid JWT: You stuck the 'Integrity Token' (starts with v4.local) instead of the JWT. The JWT must start with 'eyJ'. Please check GETTING_OAUTH.md again.")
        
        try:
            header, payload, signature = encoded_jwt.split(".")
        except ValueError:
            raise ValueError(f"Invalid JWT format. Expected 3 parts (header.payload.signature), got {len(encoded_jwt.split('.'))}.")
        try:
            # Correct padding for base64
            missing_padding = len(payload) % 4
            if missing_padding:
                payload += '=' * (4 - missing_padding)
            
            payload_decoded = urlsafe_b64decode(payload).decode("utf-8")
        except Exception as e:
            print(f"Error decoding JWT payload: {e}")
            print(f"Raw payload (masked): {payload[:5]}...{payload[-5:]}")
            raise e
        payload_dict = loads(payload_decoded)
        expiration_datetime = datetime.fromtimestamp(payload_dict["exp"])

        self._exp = expiration_datetime
        self._jwt = encoded_jwt
        
        # Extract User ID (prefer 'user_id', fallback to 'opaque_user_id')
        self._user_id = payload_dict.get("user_id", payload_dict.get("opaque_user_id"))

    @property
    def jwt(self):
        return self._jwt

    @property
    def exp(self):
        return self._exp

    @property
    def user_id(self):
        return self._user_id
