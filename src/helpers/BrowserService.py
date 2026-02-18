import json
import os
import time
import threading
import queue
import sys
from playwright.sync_api import sync_playwright

# Force unbuffered stdout
sys.stdout.reconfigure(line_buffering=True)

class BrowserService:
    def __init__(self, state_file="browser_state.json"):
        self.state_file = state_file
        self._action_queue = queue.Queue()
        self._is_running = False
        self._worker_thread = None
        
        # Internal state (only touched by worker thread)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        
        self._response_listeners = [] # List of (url_filter, callback)

    def start(self):
        """Starts the browser worker thread."""
        if self._is_running:
            return

        self._is_running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        """Stops the browser and worker thread."""
        self._execute_on_worker(self._stop_internal)
        self._is_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=2)

    def login(self, url="https://www.twitch.tv/login"):
        """Opens login page. Blocking call until page is ready."""
        if not self._is_running:
            self.start()
        return self._execute_on_worker(lambda: self._login_internal(url))

    def is_logged_in(self):
        """Checks login status."""
        return self._execute_on_worker(self._is_logged_in_internal)

    def fetch_api(self, url, method="GET", headers=None, body=None):
        """Executes API fetch via APIRequest Context (Headless request)."""
        if not self._is_running:
             self.start()
        return self._execute_on_worker(lambda: self._fetch_api_internal(url, method, headers, body))

    def fetch_in_extension_frame(self, url, headers=None):
        """Executes fetch() INSIDE the Pokemon Extension Frame (Real browser context)."""
        if not self._is_running:
             self.start()
        return self._execute_on_worker(lambda: self._fetch_in_extension_frame_internal(url, headers))

    def clear_cookies(self):
        """Clears cookies."""
        return self._execute_on_worker(self._clear_cookies_internal)
        
    def get_cookies(self):
        return self._execute_on_worker(lambda: self._context.cookies() if self._context else [])

    # --- Remote Control Methods (New) ---
    # These replace direct Page access

    def goto(self, url):
        return self._execute_on_worker(lambda: self._page.goto(url) if self._page else None)

    def click(self, selector, timeout=3000):
        return self._execute_on_worker(lambda: self._page.click(selector, timeout=timeout) if self._page else None)

    def get_content(self):
        return self._execute_on_worker(lambda: self._page.content() if self._page else "")

    def reload_page(self):
        """Reloads the current page."""
        return self._execute_on_worker(lambda: self._page.reload() if self._page else None)

    def wait_for_selector(self, selector, timeout=10000):
        return self._execute_on_worker(lambda: self._page.wait_for_selector(selector, timeout=timeout) if self._page else None)

    def capture_request_header(self, navigate_url, url_filter, header_name, timeout=20):
        """
        Navigates to a URL and waits for a request matching `url_filter`.
        Returns the value of `header_name` from that request.
        """
        return self._execute_on_worker(lambda: self._capture_request_header_internal(navigate_url, url_filter, header_name, timeout))


    # --- Internal Worker Wrapper ---

    def _execute_on_worker(self, func):
        """Queues a task for the worker thread and waits for the result."""
        if not self._is_running and func.__name__ != "_stop_internal":
             # We should probably throw or auto-restart
             pass

        result_queue = queue.Queue()
        self._action_queue.put((func, result_queue))
        
        try:
            # Wait for result
            result = result_queue.get(timeout=45) # Increased timeout for network waits
            if isinstance(result, Exception):
                print(f"BrowserService Worker Error: {result}")
                raise result
            return result
        except queue.Empty:
            print("BrowserService Worker Timeout")
            return None

    def _worker_loop(self):
        """The main loop for the worker thread."""
        print("BrowserService Worker Started", file=sys.stderr, flush=True)
        
        self._playwright = sync_playwright().start()
        
        try:
            self._launch_browser_internal()
            
            while self._is_running:
                # 1. Process all pending actions in queue
                while not self._action_queue.empty():
                    try:
                        func, result_queue = self._action_queue.get_nowait()
                        try:
                            # print(f"Executing worker task: {func}", file=sys.stderr, flush=True)
                            res = func()
                            result_queue.put(res)
                        except Exception as e:
                            print(f"Error in worker task: {e}", file=sys.stderr, flush=True)
                            result_queue.put(e)
                        finally:
                            self._action_queue.task_done()
                    except queue.Empty:
                        break

                # 2. Pump Playwright Loop (Crucial for Passive Sniffing)
                # If we just sleep or block on queue.get, network events won't fire!
                if self._page:
                    try:
                        self._page.wait_for_timeout(100) # 100ms heartbeat
                    except:
                        time.sleep(0.1)
                else:
                    time.sleep(0.1)

        except Exception as e:
            print(f"BrowserService Worker Critical Fail: {e}", file=sys.stderr, flush=True)
        finally:
            self._stop_internal()
            print("BrowserService Worker Stopped", file=sys.stderr, flush=True)

    # --- Internal Implementation Methods (Run on Worker) ---

    def _launch_browser_internal(self):
        user_data_dir = os.path.join(os.getcwd(), "browser_profile")
        if not os.path.exists(user_data_dir):
            os.makedirs(user_data_dir)

        # Merge launch and context args for persistent context
        # Stealth and Browser Args
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
            
            # Context Args
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
            self._context = self._playwright.chromium.launch_persistent_context(user_data_dir, **kwargs)
        except Exception:
            print("Chrome not found, falling back to bundled Chromium...")
            if "channel" in kwargs:
                del kwargs["channel"]
            self._context = self._playwright.chromium.launch_persistent_context(user_data_dir, **kwargs)
            
        # Persistent context has pages already? usually starts with one.
        if len(self._context.pages) > 0:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        # Disable Caching via CDP to force network requests
        try:
            client = self._context.new_cdp_session(self._page)
            client.send("Network.setCacheDisabled", {"cacheDisabled": True})
            print("Browser Cache Disabled via CDP")
            
            # Enable Low-Level Network Logging via CDP
            # This bypasses Playwright's abstraction to see RAW traffic
            client.send("Network.enable")
            client.on("Network.requestWillBeSent", self._on_cdp_request)
            client.on("Network.responseReceived", self._on_cdp_response)
            
        except Exception as e:
            print(f"Failed to setup CDP: {e}")

        # Attach centralized response listener to CONTEXT (Captures all pages/workers)
        self._context.on("response", self._handle_response_event)
        self._context.on("request", self._handle_request_event)
        self._context.on("requestfailed", self._handle_request_failed_event)
        
        # Log Service Worker Registration (Debug)
        self._context.on("serviceworker", lambda sw: print(f"Service Worker registered: {sw.url}"))

        # Stealth Scripts
        stealth_script = """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

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
        self._context.add_init_script(stealth_script)

    def _stop_internal(self):
        if self._context:
            try:
                self._context.storage_state(path=self.state_file)
            except: pass
            try:
                self._context.close()
            except: pass
            try:
                self._context.close()
            except: pass
        # Persistent context controls the browser process, so closing context closes browser.
        # self._browser is not used with launch_persistent_context
        if self._playwright:
            try:
                self._playwright.stop()
            except: pass

    def _login_internal(self, url):
        self._page.goto(url)
        return "Page Opened"

    def _is_logged_in_internal(self):
        if not self._context:
            return False
        cookies = self._context.cookies()
        for c in cookies:
             if c['name'] == 'auth-token' and c['value']:
                return True
        return False

    def _fetch_api_internal(self, url, method, headers, body):
        if not self._context:
            raise Exception("Context not ready")
        
        response = self._context.request.fetch(url, method=method, headers=headers, data=body)
        return {
            "status": response.status,
            "text": response.text(),
            "headers": response.headers,
        }

    def _fetch_in_extension_frame_internal(self, url, headers=None):
        if not self._page:
             return {"status": 500, "text": "No Page"}

        # Scroll down to ensure lazy-loaded extensions are triggered
        try:
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._page.wait_for_timeout(2000) # Increased wait time
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
            
        #print(f"Executing fetch inside Extension Frame: {target_frame.url}")
        
        # Serialize headers
        headers_js = json.dumps(headers) if headers else "{}"
        
        # Robust Fetch Script with Error Catching
        # Diagnostic Script: Log Window Properties to find the API client
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
            result = target_frame.evaluate(script)
            if result["status"] == 0:
                print(f"In-Frame Fetch JS Error: {result['text']}")
            return result
        except Exception as e:
            print(f"Frame evaluate error: {e}")
            return None
        
    def add_response_listener(self, url_filter, callback):
        """
        Registers a callback for responses matching the filter.
        callback(response_json)
        """
        if not self._is_running:
             self.start()
        self._execute_on_worker(lambda: self._response_listeners.append((url_filter, callback)))

    # --- Helper ---
    def _is_asset_url(self, url):
        """Returns True if URL is a static asset to be ignored in logs."""
        return any(url.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".css", ".js", ".svg", ".ico", ".woff", ".woff2"])

    def _handle_response_event(self, response):
        """Internal handler for all browser responses."""
        try:
            url = response.url
            
            # Debug: Print bframework URLs to verify we see them
            #if "bframework.de" in url and not self._is_asset_url(url):
                #print(f"Browser captured response: {url} (Status: {response.status})", file=sys.stderr, flush=True)

            # Check against listeners
            for url_filter, callback in self._response_listeners:
                if url_filter in url:
                    # Ignore static assets to prevent JSON errors
                    if self._is_asset_url(url):
                         continue

                    #print(f"  -> Matched listener filter: {url_filter}", file=sys.stderr, flush=True)
                    # Found a match, try to parse JSON
                    try:
                        if response.status == 200:
                            # Playwright .json() might fail if body is empty or not json
                            json_data = response.json()
                            #print(f"    -> JSON parsed successfully. Keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'List'}", file=sys.stderr, flush=True)
                            threading.Thread(target=callback, args=(url, json_data), daemon=True).start()
                        else:
                             pass
                    except Exception as e:
                        pass
        except Exception as e:
            print(f"Error in handle_response_event: {e}", file=sys.stderr, flush=True)

    def _handle_request_event(self, request):
        """Log request initiation for debugging."""
        #try:
        #    if "bframework.de" in request.url and not self._is_asset_url(request.url):
        #        print(f"Browser making request: {request.url} (Method: {request.method})", file=sys.stderr, flush=True)
        #except: pass

    def _handle_request_failed_event(self, request):
        """Log failed requests."""
        try:
            if "bframework.de" in request.url:
                print(f"Browser request FAILED: {request.url} (Error: {request.failure})", file=sys.stderr, flush=True)
        except: pass

    def _clear_cookies_internal(self):
        if self._context:
            self._context.clear_cookies()
            
    def _on_cdp_request(self, event):
        """Handle raw CDP request event."""
        try:
            req = event.get("request", {})
            url = req.get("url", "")
            if "bframework.de" in url and not self._is_asset_url(url):
                print(f"[CDP] Request: {url} (Method: {req.get('method')})", file=sys.stderr, flush=True)
        except: pass

    def _on_cdp_response(self, event):
        """Handle raw CDP response event."""
        try:
            resp = event.get("response", {})
            url = resp.get("url", "")
            if "bframework.de" in url and not self._is_asset_url(url):
                 print(f"[CDP] Response: {url} (Status: {resp.get('status')})", file=sys.stderr, flush=True)
        except: pass

    def _capture_request_header_internal(self, navigate_url, url_filter, header_name, timeout):
        """
        Sets up a request listener, navigates, and waits for a match.
        """
        found_value = [None]
        
        def handle_request(request):
            if url_filter in request.url and header_name in request.headers:
                found_value[0] = request.headers[header_name]
                
        # Attach listener
        self._page.on("request", handle_request)
        
        try:
            # Navigate only if URL is provided
            if navigate_url:
                print(f"Navigating to {navigate_url} to capture {header_name}...")
                self._page.goto(navigate_url)
            else:
                print(f"Waiting for request match on current page ({url_filter})...")
            
            # Wait loop
            start_time = time.time()
            while time.time() - start_time < timeout:
                if found_value[0]:
                    return found_value[0]
                # We need to process events... Playwright Sync does this automatically?
                # In waiting loops we usually need `page.wait_for_timeout`.
                self._page.wait_for_timeout(500)
                
            print(f"Timeout waiting for {url_filter}")
            return None
            
        finally:
            # Cleanup listener (optional but good)
            self._page.remove_listener("request", handle_request)
