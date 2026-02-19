import asyncio
import time
from os import getenv
from src.helpers.BrowserService import BrowserService
from assets.const.urls import TWITCH_URL, TWITCH_OAUTH_URL

class TwitchLoginManager:
    """
    Manages Twitch login using Playwright via BrowserService asynchronously.
    Retrieves OAuth token and Pokemon API JWT.
    """

    def __init__(self,
                 program_path,
                 twitch_connection_status_callback,
                 twitch_update_jwt_callback,
                 twitch_login_success_callback,
                 twitch_connection_timeout_callback,
                 twitch_error_callback,
                 ):

        self._program_path = program_path
        self._connection_status_callback = twitch_connection_status_callback
        self._update_jwt_callback = twitch_update_jwt_callback
        self._login_success_callback = twitch_login_success_callback
        self._connection_timeout_callback = twitch_connection_timeout_callback
        self._error_callback = twitch_error_callback

        self.browser_service = BrowserService()
        self._captured_display_name = ""

        self._login_task = None
        self._refresh_task = None

    def check_env_login(self):
        """Checks if login credentials are in environment variables"""
        username = getenv("TWITCH_USERNAME")
        oauth = getenv("TWITCH_OAUTH_TOKEN")
        jwt = getenv("TWITCH_POKEMON_JWT")

        print(f"DEBUG: Enviroment Check - Username: {username}, OAuth: {'Found' if oauth else 'Missing'}, JWT: {'Found' if jwt else 'Missing'}")

        if username and oauth:
            self._connection_status_callback({
                "username": username,
                "oauth": oauth,
            })
            if jwt:
                self._update_jwt_callback(jwt)
            return True
        return False

    def start_get_twitch_oauth_process(self):
        """Starts the login process via async Playwright."""
        if self.check_env_login():
             return

        if self._login_task is None or self._login_task.done():
            self._login_task = asyncio.create_task(self._run_browser_login())

    async def _run_browser_login(self):
        """Runs the browser login flow in a single async task."""
        try:
            print("Starting Browser Login Flow...")
            await self.browser_service.login() 
            
            print("Waiting for user to login...")
            
            logged_in = False
            for _ in range(120): # Wait up to 2 minutes
                if await self.browser_service.is_logged_in():
                    logged_in = True
                    break
                await asyncio.sleep(1)
            
            if not logged_in:
                print("Login timed out or failed.")
                self._connection_timeout_callback()
                return

            print("Login detected! Fetching credentials...")
            self._login_success_callback()
            
            print("Fetching Credentials from cookies...")
            cookies = await self.browser_service.get_cookies()
            username = next((c['value'] for c in cookies if c['name'] == 'name' or c['name'] == 'login'), "unknown_user")
            
            auth_token = next((c['value'] for c in cookies if c['name'] == 'auth-token'), None)
            
            env_oauth = getenv("TWITCH_OAUTH_TOKEN")
            if env_oauth:
                print("Using OAuth token from env.")
                final_oauth = env_oauth
            elif auth_token:
                print("Using 'auth-token' cookie as OAuth token.")
                if not auth_token.startswith("oauth:"):
                    final_oauth = f"oauth:{auth_token}"
                else:
                    final_oauth = auth_token
            else:
                print("WARNING: No OAuth token found in Env or Cookies. Chat will likely fail.")
                final_oauth = ""
            
            self._connection_status_callback({
                "username": username,
                "oauth": final_oauth, 
            })

            target_channel = getenv("TWITCH_CHANNEL", getenv("TWITCH_USERNAME"))
            print(f"Fetching Pokemon JWT from channel: {target_channel}...")
            print("!!! PLEASE NAVIGATE TO THE TARGET CHANNEL IF NOT ALREADY THERE !!!")
            
            jwt = await self.browser_service.capture_request_header(
                navigate_url=None, 
                url_filter="poketwitch.bframework.de",
                header_name="authorization", 
                timeout=60.0
            ) 
            
            if not jwt:
                jwt = await self.browser_service.capture_request_header(
                    navigate_url=None,
                    url_filter="poketwitch.bframework.de",
                    header_name="Authorization",
                    timeout=10.0
                )
                
            if jwt:
                print("Captured JWT from request!")
                self._update_jwt_callback(jwt)
            else:
                print("Could not capture JWT (timeout).")

        except Exception as e:
            print(f"Browser Login Error: {e}")
            self._error_callback()

    def get_twitch_jwt(self):
        """Called when JWT needs refresh."""
        if self.check_env_login():
            return
            
        print("Refreshing Pokemon JWT via Browser Reload...")
        
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_jwt_background())

    async def _refresh_jwt_background(self):
        """Async task for refreshing JWT"""
        try:
            await self.browser_service.reload_page()
            
            jwt = await self._attempt_capture_jwt(timeout=45.0)
            
            if not jwt:
                print("JWT Capture failed on first attempt. Checking for interruptions...")
                clicked = await self._handle_stream_interruptions()
                
                if clicked:
                    print("Interruption handled. Waiting for JWT again...")
                    jwt = await self.browser_service.capture_request_header(
                        navigate_url=None, 
                        url_filter="poketwitch.bframework.de",
                        header_name="authorization", 
                        timeout=30.0
                    )
            
            if not jwt:
                 print("JWT Capture still failed. Retrying Reload (Attempt 2)...")
                 await self.browser_service.reload_page()
                 await asyncio.sleep(5)
                 jwt = await self._attempt_capture_jwt(timeout=45.0)

            if jwt:
                 print("Refreshed JWT captured!")
                 self._update_jwt_callback(jwt)
            else:
                 print("Failed to capture Refreshed JWT after retries.")
                 self._error_callback()

        except Exception as e:
            print(f"Error refreshing JWT: {e}")
            self._error_callback()

    async def _attempt_capture_jwt(self, timeout):
        """Helper to capture JWT with primary and fallback headers"""
        jwt = await self.browser_service.capture_request_header(
             navigate_url=None,
             url_filter="poketwitch.bframework.de",
             header_name="authorization", 
             timeout=timeout
        )
        if not jwt:
            jwt = await self.browser_service.capture_request_header(
                 navigate_url=None,
                 url_filter="poketwitch.bframework.de",
                 header_name="Authorization",
                 timeout=10.0
            )
        return jwt

    async def _handle_stream_interruptions(self):
        """Checks for common stream interruptions and clicks them via playwright."""
        page = self.browser_service._page
        if not page: return False
        
        clicked = False
        interruption_selectors = [
            '[data-a-target="player-overlay-mature-accept"]', 
            '[data-a-target="content-classification-gate-overlay-start-watching-button"]',
            'button[aria-label="Start Watching"]',
            'button:has-text("Start Watching")'
        ]
        
        for selector in interruption_selectors:
            if await page.is_visible(selector):
                print(f"Found interruption button: {selector}. Clicking...")
                await page.click(selector)
                clicked = True
                await asyncio.sleep(2)
        
        return clicked

    def request_twitch_login(self):
        """User requested manual login."""
        self.start_get_twitch_oauth_process()

    async def close_web_async(self):
        await self.browser_service.stop()

    def close_web(self):
        # Fallback if called synchronously
        asyncio.create_task(self.close_web_async())
        
    async def clear_cookies(self):
        await self.browser_service.clear_cookies()
