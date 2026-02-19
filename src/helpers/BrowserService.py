import json
import os
import asyncio
import sys
from playwright.async_api import async_playwright

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

class BrowserService:
    def __init__(self, state_file="browser_state.json"):
        self.state_file = state_file
        self._is_running = False
        
        # Internal state
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        
        self._response_listeners = [] # List of (url_filter, callback)

    async def start(self):
        """Starts the async browser."""
        if self._is_running:
            return

        self._is_running = True
        self._playwright = await async_playwright().start()
        await self._launch_browser_internal()

    async def stop(self):
        """Stops the browser."""
        await self._stop_internal()
        self._is_running = False

    async def login(self, url="https://www.twitch.tv/login"):
        """Opens login page."""
        if not self._is_running:
            await self.start()
        if self._page:
            await self._page.goto(url)
        return "Page Opened"

    async def is_logged_in(self):
        """Checks login status."""
        if not self._context:
            return False
        cookies = await self._context.cookies()
        for c in cookies:
             if c['name'] == 'auth-token' and c['value']:
                return True
        return False

    async def fetch_api(self, url, method="GET", headers=None, body=None):
        """Executes API fetch via APIRequest Context (Headless request)."""
        if not self._is_running:
             await self.start()
        
        if not self._context:
            raise Exception("Context not ready")
        
        response = await self._context.request.fetch(url, method=method, headers=headers, data=body)
        return {
            "status": response.status,
            "text": await response.text(),
            "headers": response.headers,
        }

    async def fetch_in_extension_frame(self, url, headers=None):
        """Executes fetch() INSIDE the Pokemon Extension Frame (Real browser context)."""
        if not self._is_running:
             await self.start()
        
        if not self._page:
             return {"status": 500, "text": "No Page"}

        # Scroll down to ensure lazy-loaded extensions are triggered
        try:
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._page.wait_for_timeout(2000) # Increased wait time
        except:
             pass

        target_frame = None
        frames_debug = []
        for frame in self._page.frames:
            frames_debug.append(frame.url)
            # Match the extension ID or domain
            if "pm0qkv9g4h87t5y6lg329oam8j7ze9" in frame.url:
                target_frame = frame
                break
        
        if not target_frame:
             print("Extension frame not found!")
             print("Found frames:", frames_debug)
             return {"status": 404, "text": f"Frame not found. Visible frames: {len(frames_debug)}"}
            
        # Serialize headers
        headers_js = json.dumps(headers) if headers else "{}"
        
        script = f"""
        async () => {{
            try {{
                const res = await fetch("{url}", {{
                    method: "GET",
                    headers: {headers_js}
                }});
                const text = await res.text();
                return {{
                    status: res.status,
                    text: text,
                    headers: {{}} 
                }};
            }} catch (e) {{
                return {{
                    status: 0,
                    text: "JS Error: " + e.name + ": " + e.message
                }};
            }}
        }}
        """
        try:
            # We use target_frame.evaluate to run inside that specific frame context
            result = await target_frame.evaluate(script)
            if result["status"] == 0:
                print(f"In-Frame Fetch JS Error: {result['text']}")
            return result
        except Exception as e:
            print(f"Frame evaluate error: {e}")
            return None

    async def clear_cookies(self):
        """Clears cookies."""
        if self._context:
            await self._context.clear_cookies()
        
    async def get_cookies(self):
        return await self._context.cookies() if self._context else []

    async def goto(self, url):
        if self._page:
            await self._page.goto(url)

    async def click(self, selector, timeout=3000):
        if self._page:
            await self._page.click(selector, timeout=timeout)

    async def get_content(self):
        if self._page:
            return await self._page.content()
        return ""

    async def reload_page(self):
        """Reloads the current page."""
        if self._page:
            await self._page.reload()

    async def wait_for_selector(self, selector, timeout=10000):
        if self._page:
            await self._page.wait_for_selector(selector, timeout=timeout)

    async def capture_request_header(self, navigate_url, url_filter, header_name, timeout=20):
        """
        Navigates to a URL and waits for a request matching `url_filter`.
        Returns the value of `header_name` from that request.
        """
        found_value = None
        event_match = asyncio.Event()

        async def handle_request(request):
            nonlocal found_value
            if url_filter in request.url and header_name in request.headers:
                found_value = request.headers[header_name]
                event_match.set()

        self._page.on("request", handle_request)
        try:
            if navigate_url:
                print(f"Navigating to {navigate_url} to capture {header_name}...")
                await self._page.goto(navigate_url)
            else:
                print(f"Waiting for request match on current page ({url_filter})...")
            
            try:
                await asyncio.wait_for(event_match.wait(), timeout=timeout)
                return found_value
            except asyncio.TimeoutError:
                print(f"Timeout waiting for {url_filter}")
                return None
        finally:
            self._page.remove_listener("request", handle_request)

    def add_response_listener(self, url_filter, callback):
        """
        Registers a callback for responses matching the filter.
        callback is an async function: async def callback(url, response_json)
        """
        self._response_listeners.append((url_filter, callback))

    # --- Internal Implementation Methods ---

    async def _launch_browser_internal(self):
        user_data_dir = os.path.join(os.getcwd(), "browser_profile")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        kwargs = {
            "headless": False, 
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disk-cache-size=1"
            ],
            "ignore_default_args": ["--enable-automation"],
            "channel": "chrome",
            
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 1440},
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
            "locale": "en-US",
            "timezone_id": "Europe/Berlin", 
            "permissions": ["geolocation"],
            "geolocation": {"latitude": 52.52, "longitude": 13.405},
            "extra_http_headers": {
                "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Linux"'
            }
        }

        try:
            self._context = await self._playwright.chromium.launch_persistent_context(user_data_dir, **kwargs)
        except Exception:
            print("Chrome not found, falling back to bundled Chromium...")
            if "channel" in kwargs:
                del kwargs["channel"]
            self._context = await self._playwright.chromium.launch_persistent_context(user_data_dir, **kwargs)
            
        if len(self._context.pages) > 0:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        try:
            client = await self._context.new_cdp_session(self._page)
            await client.send("Network.setCacheDisabled", {"cacheDisabled": True})
            print("Browser Cache Disabled via CDP")
        except Exception as e:
            print(f"Failed to setup CDP: {e}")

        self._context.on("response", self._handle_response_event)
        
        stealth_script = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
            Promise.resolve({ state: 'denied' }) :
            Promise.resolve({ state: 'granted' })
        );
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (NVIDIA)';
            if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060/PCIe/SSE2, OpenGL 4.5.0)';
            return getParameter(parameter);
        };
        """
        await self._context.add_init_script(stealth_script)

    async def _stop_internal(self):
        if self._context:
            try:
                await self._context.storage_state(path=self.state_file)
            except: pass
            try:
                await self._context.close()
            except: pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except: pass

    # --- Helper ---
    def _is_asset_url(self, url):
        return any(url.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".css", ".js", ".svg", ".ico", ".woff", ".woff2"])

    def _handle_response_event(self, response):
        try:
            url = response.url
            for url_filter, callback in self._response_listeners:
                if url_filter in url:
                    if self._is_asset_url(url):
                         continue
                    if response.status == 200:
                        # Schedule coroutine execution
                        asyncio.create_task(self._parse_and_call(response, callback, url))
        except Exception as e:
            print(f"Error in handle_response_event: {e}", file=sys.stderr, flush=True)

    async def _parse_and_call(self, response, callback, url):
        try:
            json_data = await response.json()
            await callback(url, json_data)
        except Exception:
            pass
