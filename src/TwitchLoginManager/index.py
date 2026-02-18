from threading import Thread
import time
from os import getenv
from PyQt6.QtCore import QObject, pyqtSlot
from src.helpers.BrowserService import BrowserService
from assets.const.urls import TWITCH_URL, TWITCH_OAUTH_URL

class TwitchLoginManager(QObject):
    """
    Manages Twitch login using Playwright via BrowserService.
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

        super().__init__()
        self._program_path = program_path
        self._connection_status_callback = twitch_connection_status_callback
        self._update_jwt_callback = twitch_update_jwt_callback
        self._login_success_callback = twitch_login_success_callback
        self._connection_timeout_callback = twitch_connection_timeout_callback
        self._error_callback = twitch_error_callback

        self.browser_service = BrowserService()
        self._captured_display_name = ""

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
        """Starts the login process via Playwright."""
        if self.check_env_login():
             # Even if we have env login, we might need the browser for fetching data later.
             # But for now, let's assume if env is present, we are good.
             return

        Thread(target=self._run_browser_login).start()

    def _run_browser_login(self):
        """Runs the browser login flow in a separate thread."""
        try:
            print("Starting Browser Login Flow...")
            page = self.browser_service.login() 
            
            # 1. Wait for Login
            # We assume user logs in. We can check for a specific cookie or element.
            # Simple check: url changes to twitch.tv (home) or dashboard
            print("Waiting for user to login...")
            
            # Poll for login success (e.g. check for auth-token cookie)
            logged_in = False
            for _ in range(120): # Wait up to 2 minutes
                if self.browser_service.is_logged_in():
                    logged_in = True
                    break
                time.sleep(1)
            
            if not logged_in:
                print("Login timed out or failed.")
                self._connection_timeout_callback()
                return

            print("Login detected! Fetching credentials...")
            self._login_success_callback()
            
            # 2. Get OAuth Token (for Chat)
            # Navigate to twitchapps.com/tmi/
            print("Fetching OAuth Token...")
            # 2. Get Username and OAuth from Cookies
            print("Fetching Credentials from cookies...")
            cookies = self.browser_service.get_cookies()
            username = next((c['value'] for c in cookies if c['name'] == 'name' or c['name'] == 'login'), "unknown_user")
            
            # Extract auth-token for Chat
            auth_token = next((c['value'] for c in cookies if c['name'] == 'auth-token'), None)
            
            # Prefer Env Token if present, otherwise use Cookie Token
            env_oauth = getenv("TWITCH_OAUTH_TOKEN")
            if env_oauth:
                print("Using OAuth token from env.")
                final_oauth = env_oauth
            elif auth_token:
                print("Using 'auth-token' cookie as OAuth token.")
                # Ensure it starts with "oauth:" (IRC standard)
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

            # 3. Get Pokemon JWT
            target_channel = getenv("TWITCH_CHANNEL", getenv("TWITCH_USERNAME"))
            print(f"Fetching Pokemon JWT from channel: {target_channel}...")
            print("!!! PLEASE NAVIGATE TO THE TARGET CHANNEL IF NOT ALREADY THERE !!!")
            
            # Use the new helper method in BrowserService
            # We filter by the domain 'poketwitch.bframework.de' to catch ANY extension call
            # We set navigate_url=None to let the user navigate, preventing cookie invalidation.
            jwt = self.browser_service.capture_request_header(
                navigate_url=None, 
                url_filter="poketwitch.bframework.de",
                header_name="authorization", 
                timeout=60 # Give user time to navigate
            ) 
            
            # Playwright header keys might be lowercased automatically. 
            # If not found, try "Authorization" (Title case)
            if not jwt:
                jwt = self.browser_service.capture_request_header(
                    navigate_url=None,
                    url_filter="poketwitch.bframework.de",
                    header_name="Authorization",
                    timeout=10 # Short timeout for second check
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
        # Check env first
        if self.check_env_login():
            return
            
        print("Refreshing Pokemon JWT via Browser Reload...")
        # 1. Reload the page
        self.browser_service.reload_page()
        
        # 2. Wait for new JWT
        # We need to run this in a thread or ensure capture_request_header doesn't block the UI thread if called from Main Thread
        # But get_twitch_jwt is called from MainApplication, so blocking here blocks the UI.
        # Ideally, this should be async or run in a thread.
        # MainApplication calls this: self.TwitchLoginManager.get_twitch_jwt() inside _get_twitch_jwt() inside main_thread() ??
        # No, _get_twitch_jwt() is triggered by timer.
        # If we block here, the GUI freezes.
        # We should start a thread here.
        
        Thread(target=self._refresh_jwt_background).start()

    def _refresh_jwt_background(self):
        """Background thread for refreshing JWT"""
        try:
            # Attempt 1
            jwt = self._attempt_capture_jwt(timeout=45)
            
            if not jwt:
                print("JWT Capture failed on first attempt. Checking for interruptions...")
                # Check for "Start Watching" or "Mature" content buttons that block the player
                # We need to run these checks on the worker thread
                clicked = self.browser_service._execute_on_worker(lambda: self._handle_stream_interruptions())
                
                if clicked:
                    print("Interruption handled. Waiting for JWT again...")
                    jwt = self.browser_service.capture_request_header(
                        navigate_url=None, 
                        url_filter="poketwitch.bframework.de",
                        header_name="authorization", 
                        timeout=30
                    )
            
            if not jwt:
                 print("JWT Capture still failed. Retrying Reload (Attempt 2)...")
                 self.browser_service.reload_page()
                 time.sleep(5)
                 jwt = self._attempt_capture_jwt(timeout=45)

            if jwt:
                 print("Refreshed JWT captured!")
                 self._update_jwt_callback(jwt)
            else:
                 print("Failed to capture Refreshed JWT after retries.")
                 self._error_callback()

        except Exception as e:
            print(f"Error refreshing JWT: {e}")
            self._error_callback()

    def _attempt_capture_jwt(self, timeout):
        """Helper to capture JWT with primary and fallback headers"""
        jwt = self.browser_service.capture_request_header(
             navigate_url=None,
             url_filter="poketwitch.bframework.de",
             header_name="authorization", 
             timeout=timeout
        )
        if not jwt:
            jwt = self.browser_service.capture_request_header(
                 navigate_url=None,
                 url_filter="poketwitch.bframework.de",
                 header_name="Authorization",
                 timeout=10
            )
        return jwt

    def _handle_stream_interruptions(self):
        """
        Checks for common stream interruptions (Mature content warning, 'Start Watching') 
        and clicks them to resume playback/loading extensions.
        RUN THIS ON WORKER THREAD.
        """
        page = self.browser_service._page
        if not page: return False
        
        clicked = False
        # Selectors for "Start Watching" or "Agree to Mature" buttons
        interruption_selectors = [
            '[data-a-target="player-overlay-mature-accept"]', 
            '[data-a-target="content-classification-gate-overlay-start-watching-button"]',
            'button[aria-label="Start Watching"]',
            'button:has-text("Start Watching")'
        ]
        
        for selector in interruption_selectors:
            if page.is_visible(selector):
                print(f"Found interruption button: {selector}. Clicking...")
                page.click(selector)
                clicked = True
                time.sleep(2) # Wait for click effect
        
        return clicked

    def request_twitch_login(self):
        """User requested manual login."""
        self.start_get_twitch_oauth_process()

    def close_web(self):
        self.browser_service.stop()
        
    def clear_cookies(self):
        """Clears browser cookies."""
        self.browser_service.clear_cookies()
