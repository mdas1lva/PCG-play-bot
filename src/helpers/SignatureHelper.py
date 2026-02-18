import time
import uuid
import hmac
import hashlib
from urllib.parse import urlparse

class SignatureHelper:
    """
    Helper class to generate signatures for PCG API requests.
    Reverse-engineered from index-CylrMLvu.js
    """

    @staticmethod
    def get_pcg_headers(twitch_user_id, full_url, auth_token):
        """
        Generates the required headers for a signed request.
        
        Args:
            twitch_user_id (str): The Twitch User ID.
            full_url (str): The full URL of the API endpoint.
            auth_token (str): The JWT auth token (without 'Bearer ' prefix).
            
        Returns:
            dict: A dictionary containing the necessary headers.
        """
        
        # 1. Constants found in the JS file
        secret_part_1 = "d4o3"
        secret_part_2 = "2t5X"
        secret = f"{secret_part_1}n{secret_part_2}"  # d4o3n2t5X
        
        # 2. Prepare dynamic values
        # The game calculates timestamp as: Math.floor(Date.now()/1e3) + serverOffset
        # We assume local clock is correct. If strict usage fails, we might need NTP or server offset.
        timestamp = str(int(time.time()))
        
        # Generate a standard UUID v4 for the nonce (JS uses 'ae()' which is uuid.v4)
        nonce = str(uuid.uuid4())
        
        # Extract the path from the URL.
        # JS uses: new URL(url, location.origin).pathname
        # This handles absolute URLs correctly.
        # Example: https://poketwitch.bframework.de/api/game/ext/trainer/pokedex/info/v2/?pokedex_id=354
        # Path: /api/game/ext/trainer/pokedex/info/v2/
        path = urlparse(full_url).path
        
        # 3. Construct the "Message" to sign
        # Logic from JS: `${UserID}:${Timestamp}X${Path}:${Nonce}`
        # Confirmed via decompilation: const Ve=`${Q}:${me}X${J}:${je}`
        # Where Q=UserID, me=Timestamp (swapped var in minified call), J=Path, je=Nonce
        # Wait, previous analysis:
        # oe(Gt.value, je, Ve, me)  -> oe(Args: 1, 2, 3, 4)
        # 1=UserID, 2=Timestamp, 3=Path, 4=Nonce
        # Ve = `${1}:${2}X${3}:${4}` -> UserID:TimestampXPath:Nonce
        message = f"{twitch_user_id}:{timestamp}X{path}:{nonce}"
        
        #print(f"DEBUG SIGNATURE GEN:")
        #print(f"  Inputs: UserID={twitch_user_id}, Time={timestamp}, Path={path}, Nonce={nonce}")
        #print(f"  Secret: {secret}")
        #print(f"  Message: {message}")
        
        # 4. Generate Signature (HMAC-SHA256)
        signature = hmac.new(
            secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        #print(f"  Signature: {signature}")
        
        # 5. Return the headers
        return {
            "Authorization": f"Bearer {auth_token}", # Assuming standard Bearer format (JS might send raw token in Authorization?? No, likely Bearer)
            # WAIT. JS sends: headers.Authorization = ... (depends on Axios default).
            # Usually axios defaults Authorization to whatever is set in `defaults.headers.common`.
            # But specific endpoints might override.
            # My 'PokemonData' sends raw token in 'Authorization'.
            # I will stick to what `PokemonData` used before unless proven otherwise.
            # Actually catch: `old_headers` used `self._poke_jwt.jwt` (Raw).
            # If I put "Bearer " here, it might break if serve expects raw.
            # BUT standard OAuth is usually Bearer.
            # Let's check `PokemonData` usage.
            # In `PokemonData.py`, it constructs headers with `self._poke_jwt.jwt`.
            "Authorization": auth_token, # Send RAW token as seen in JS (W.defaults.headers.common.Authorization = L.value)
            "signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
            "clientVersion": "1.4.3.1", # Matches JS variable, even if URL is 1.4.4
            "Accept": "application/json, text/plain, */*",
        }

# def auth_val_final(token):
#     # If token already has Bearer, use it.
#     if token.startswith("Bearer "):
#         return token
#     return f"Bearer {token}" # Most likely it needs Bearer.
