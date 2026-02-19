import re
from datetime import datetime
from threading import Thread, Event
import json
from dateutil import parser, tz
from src.helpers.SignatureHelper import SignatureHelper

from assets.const.urls import POKEMON_EXTENSION_URL, POKEMON_SPAWN_URL


class PokemonData:
    """
    This class is responsible to deal with user's pokemon game data.
    It will fetch useful user data like captured pokemons, user's inventory and missions. It also should contain a
    pokedex data to handle pokemon spawns from chat.
    """

    def __init__(self, poke_data_update_callback, poke_data_error_callback, browser_service):

        self._poke_jwt = None
        self._browser_service = browser_service
        self._jwt_refreshed = Event() # Synchronization for token refresh
        self._jwt_refreshed.set() # Initially set as valid

        self._data_update_callback = poke_data_update_callback
        self._data_error_callback = poke_data_error_callback

        self._update_thread = None
        
        # Register Passive Listener for API data
        self._browser_service.add_response_listener("poketwitch.bframework.de", self._on_browser_response)

        self._captured = {
            "total_count": 0,
            "unique_captured_ids": [],
            "unique_count": 0,
            "shiny_count": 0,
            "buddy_types": [],
        }

        self._inventory = {
            "cash": 0,
            "items": [],
        }

        self._missions = {
            "end_date": "",
            "missions": [],
            "target_missions": [],
        }

        self._pokedex = {
            "dex": [],
            "total_count": 0,
            "total_progress": 0,
            "spawn_count": 0,
            "spawn_progress": 0,
        }
        
        self._buddy_details_cache = {
             "pokedex_id": None,
             "data": None
        }

    def update_poke_jwt(self, new_value):
        """Updates instance's pokemon API JWT to fetch requests"""

        self._poke_jwt = new_value
        if new_value:
             self._jwt_refreshed.set() # Unblock waiting threads

    def update_data(self):
        """Start thread to fetch user's pokemon data"""
        
        # Active fetch enabled with Signed Requests
        if self._poke_jwt is not None:
             # Ensure we don't start multiple threads if already running? 
             # The original code just started it.
             self._update_thread = Thread(target=self._update_data_thread)
             self._update_thread.start()

    def _update_data_thread(self):
        """Fetches user's data in a thread"""

        print("Updating pokemon data (Active Signed Fetch)...")

        captured = handle_captured_data(self._fetch_api_data("pokemon/v2/"), self.get_pokemon_data, self._buddy_details_cache)
        self._captured = captured if captured is not None else self._captured

        inventory = handle_inventory_data(self._fetch_api_data("inventory/v3/"))
        self._inventory = inventory if inventory is not None else self._inventory

        missions = handle_missions_data(self._fetch_api_data("mission/v2/"))
        self._missions = missions if missions is not None else self._missions

        pokedex = handle_pokedex_data(self._fetch_api_data("pokedex/v2/"))
        self._pokedex = pokedex if pokedex is not None else self._pokedex

        self._data_update_callback()

    def _fetch_api_data(self, data_type, custom_headers=None, retry_count=0):
        """Fetches user's data from API server using BrowserService"""

        if self._poke_jwt is None:
            return None

        # Determine correct Authorization header format
        # User provided request shows RAW JWT (No Bearer)
        auth_val = self._poke_jwt.jwt
        
        # Append trailing slash if missing (standardize)
        # Append trailing slash if missing (standardize), but NOT if query params exist
        if not data_type.endswith("/") and "?" not in data_type:
            data_type += "/"

        url_endpoint = data_type
        # Ensure url_endpoint contains query params if they were passed in data_type
        
        url = f"{POKEMON_EXTENSION_URL}/{url_endpoint}"

        # Headers for the extension frame
        if custom_headers:
            headers = custom_headers
        else:
            # Default headers: ALWAYS SIGNED
            try:
                 user_id = self._poke_jwt.user_id
                 # Generate signed headers using Raw Token
                 headers = SignatureHelper.get_pcg_headers(str(user_id), url, auth_val)
            except Exception as e:
                 print(f"Error generating signature for {url}: {e}")
                 # Fallback to legacy headers (will likely fail but safe fallback)
                 headers = {
                    "Authorization": auth_val,
                    "Accept": "application/json, text/plain, */*",
                    "clientVersion": "1.4.3.1"
                 }

        try:
            # Use the In-Frame Fetch with improved debug logging
            response = self._browser_service.fetch_in_extension_frame(url, headers=headers)
            
            if response and response["status"] == 200:
                try:
                    return json.loads(response["text"])
                except:
                    print(f"Error parsing JSON from {url}")
                    return None
            else:
                code = response["status"] if response else "Unknown"
                text = response["text"] if response else ""
                
                # Check for specific "Invalid Signature" error
                if code == 400 and '"error":-20' in text.replace(" ", ""):
                    print(f"Verified: Signature required for {data_type}. Treating as 'New Pokemon' fallback.")
                    return None

                # Check for Token Expired
                if code == 400 and '"error":-24' in text.replace(" ", ""):
                     print("Pokemon API: Token Expired. Triggering Refresh...")
                     
                     if retry_count == 0:
                         self._jwt_refreshed.clear()
                         self._data_error_callback(-24)
                         
                         print("Waiting for JWT Refresh (Max 60s)...")
                         if self._jwt_refreshed.wait(timeout=60):
                             print("JWT Refreshed! Retrying request...")
                             # Recursive retry with STARTING FRESH (to regenerate headers with new token)
                             return self._fetch_api_data(data_type, custom_headers=None, retry_count=1)
                         else:
                             print("Wait for JWT Refresh timed out.")
                             return None
                     else:
                         print("Retry failed for Token Expiration. Giving up.")
                         return None
                    
                print(f"Pokemon data request error for {data_type}. Status code: {code}")
                print(f"Response Body: {text}") # Log the error reason!
                return None
                
        except Exception as e:
            # Suppress "Event loop is closed" errors during shutdown
            if "Event loop" not in str(e) and "stopped" not in str(e):
                print(f"Pokemon API Request Error: {e}", file=sys.stderr, flush=True)
            self._data_error_callback(None)
            return None

    def _on_browser_response(self, url, json_data):
        """Callback for passive data sniffing from browser."""
        # print(f"Captured Data from: {url}")
        
        if "pokemon/v2" in url:
            print("Captured Passive: Pokemon List")
            captured = handle_captured_data(json_data, self.get_pokemon_data, self._buddy_details_cache)
            self._captured = captured if captured is not None else self._captured
            self._data_update_callback()
            
        elif "inventory/v3" in url:
             print("Captured Passive: Inventory")
             inventory = handle_inventory_data(json_data)
             self._inventory = inventory if inventory is not None else self._inventory
             self._data_update_callback()
             
        elif "mission/v2" in url:
             print("Captured Passive: Missions")
             missions = handle_missions_data(json_data)
             self._missions = missions if missions is not None else self._missions
             self._data_update_callback()
             
        elif "pokedex/v2" in url:
             print("Captured Passive: Pokedex")
             pokedex = handle_pokedex_data(json_data)
             self._pokedex = pokedex if pokedex is not None else self._pokedex
             self._data_update_callback()

    def get_pokemon_data(self, pokedex_id):
        """Fetches specific pokemon data from API server"""

        # 1. Check Local Cache (Captured Pokemon)
        if self._captured and "all_pokemon_raw" in self._captured:
            for p in self._captured["all_pokemon_raw"]:
                if p["pokedexId"] == pokedex_id:
                    # Found it! Return formatted data ONLY if we have minimal data
                    # User requested to abort if Tier is missing.
                    # If tier is missing in cache, we should try to FETCH it.
                    # So we only return here if we have what we need.
                    
                    if "tier" in p:
                        def get_pokemon_types(type1, type2):
                            types = [type1, type2]
                            return list(filter(lambda x: x != "none" and x is not None, types))
                            
                        return {
                            "pokedex_id": p["pokedexId"],
                            "name": p["name"],
                            "weight": p.get("weight", 0), 
                            "types": get_pokemon_types(p.get("type1"), p.get("type2")), 
                            "tier": p["tier"], 
                            "base_stats": p.get("baseStats", 0),
                            "base_hp": p.get("hp", 0),
                            "base_speed": p.get("speed", 0),
                        }
                    else:
                        # Cached data is incomplete (missing tier). 
                        # Fall through to Fetch to get complete data.
                        print(f"Cached data for {p['name']} is missing Tier. Attempting to fetch...")
                        break 
                    
        # 2. If not found locally (or incomplete), try fetch (for new pokemon)
        try:
             # Using the correct endpoint provided by user
             url_endpoint = f"pokedex/info/v2/?pokedex_id={pokedex_id}"
             
             # Fetch API Data (Now automatically signed by _fetch_api_data)
             data = self._fetch_api_data(url_endpoint)
             
             if data:
                 # print(f"Verified: Successfully fetched signed data for ID {pokedex_id}.")
                 return handle_pokemon_data(data)
             else:
                pass # Fallback to abort

        except Exception as e:
             print(f"Error fetching signed data: {e}")
             pass
             
        # 3. Fallback (Abort Mode)
        # User requested to abort if data is missing so we can fix it.
        print(f"Critical Error: Could not fetch details for ID {pokedex_id}. Aborting catch attempt.")
        return None

    def check_inventory(self, item_name):
        """Checks if item exists in inventory"""

        return any(item.get("sprite_name") == item_name for item in self.inventory["items"])

    def get_last_spawn_data(self):
        """Fetches last spawn data from API server"""
        
        # Access through instance method if needed, but this is a static method in original code
        # However, static methods can't access self._browser_service.
        # We should convert this to an instance method or pass browser service.
        # Since it's used by LogicDealer via MainApplication callback, let's see how it's called.
        # MainApplication passes: self.last_spawn_data_callback
        # def last_spawn_data_callback(self, spawn_data): self.HomePage.update_last_spawn(...)
        # Wait, where is `get_last_spawn_data` called?
        # It's called by main_thread logic or LogicDealer?
        # Actually in the original code it was `@staticmethod`.
        # LogicDealer calls it?
        pass

    @property
    def captured(self):
        return self._captured

    @property
    def inventory(self):
        return self._inventory

    @property
    def missions(self):
        return self._missions

    @property
    def pokedex(self):
        return self._pokedex


# We need to handle `get_last_spawn_data` which was static.
# It uses POKEMON_SPAWN_URL.
# Ideally, we move this logic to use browser service too.
# But since I can't easily change the architecture of callers (LogicDealer?) without checking,
# I will keep a standalone function or restoration of requests for this ONE public endpoint if it works.
# If `POKEMON_SPAWN_URL` is public, `requests` is fine.
# "https://poketwitch.bframework.de/api/game/spawn/last" looks public.
# Let's import requests just for this one fallback or use BrowserService if we can access the instance.
# But `get_last_spawn_data` was static. 
# I will change it to a module-level function or keep it static but using requests.

import requests
def get_last_spawn_data_static():
    """Fetches last spawn data from API server (Static/Module level)"""
    try:
        response = requests.get(POKEMON_SPAWN_URL, timeout=10)
        if response.status_code == 200:
            return handle_last_spawn_data(response.json())
        else:
            print(f"Spawn data request error. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"Spawn data error: {e}")
        return None

# Helpers
def handle_captured_data(server_data, get_pokemon_data, buddy_cache=None):
    """Treats fetched captured pokemon data"""

    if server_data is None:
        return None

    data = {
        "total_count": len(server_data["allPokemon"]),
        "unique_captured_ids": [],
        "unique_count": 0,
        "shiny_count": 0,
        "buddy_types": [],
        "all_pokemon_raw": server_data["allPokemon"] # Store raw list for lookup
    }

    for pokemon in server_data["allPokemon"]:

        if pokemon["pokedexId"] not in data["unique_captured_ids"]:
            data["unique_captured_ids"].append(pokemon["pokedexId"])
            data["unique_count"] = data["unique_count"] + 1

        if pokemon["isShiny"]:
            data["shiny_count"] = data["shiny_count"] + 1

        if pokemon.get("isBuddy", False):
            buddy_data = None
            # Check cache if available
            if buddy_cache and buddy_cache.get("pokedex_id") == pokemon["pokedexId"] and buddy_cache.get("data"):
                 buddy_data = buddy_cache["data"]
            else:
                 # Not cached or changed, fetch logic (via helper)
                 buddy_data = get_pokemon_data(pokemon["pokedexId"])
                 # Update cache
                 if buddy_cache is not None and buddy_data is not None:
                     buddy_cache["pokedex_id"] = pokemon["pokedexId"]
                     buddy_cache["data"] = buddy_data

            if buddy_data is not None:
                data["buddy_types"] = buddy_data["types"]

    return data


def handle_inventory_data(server_data):
    """Treats fetched inventory data"""

    if server_data is None:
        return None

    data = {
        "cash": server_data["cash"],
        "items": [
            {"name": item["name"], "amount": item["amount"], "sprite_name": item.get("sprite_name", item.get("name", "Unknown"))}
            for item in server_data["allItems"]
        ]
    }

    return data


def handle_missions_data(server_data):
    """Treats fetched missions data"""

    if server_data is None:
        return None

    data = {
        "end_date": server_data["endDate"],
        "missions": [
            {"name": item["name"], "goal": item["goal"], "progress": item["progress"]}
            for item in server_data["missions"]
        ],
        "target_missions": [],
    }

    pokemon_types = [
        "normal", "fighting", "rock", "fire", "poison", "ghost", "water", "ground", "dragon",
        "grass", "flying", "dark", "electric", "psychic", "psychic", "ice", "bug", "fairy"
    ]

    data["target_missions"] = []
    for mission in data["missions"]:

        mission_name = mission["name"].lower()

        if "catch" in mission_name and "miss" not in mission_name and mission["progress"] < mission["goal"]:

            # Tier
            if "tier" in mission_name:
                match = re.search(r"tier\s+(\w)", mission_name)
                if match:
                    data["target_missions"].append(("tier", match.group(1)))
                    continue

            # BST
            if "bst" in mission_name:
                match = re.findall(r"\d+", mission_name)
                if len(match) > 0:
                    if "greater" in mission_name or "higher" in mission_name:
                        data["target_missions"].append(("bst_greater", match[1]))
                        continue
                    elif "lower" in mission_name:
                        data["target_missions"].append(("bst_lower", match[1]))
                        continue

            # Weight
            if re.search(r"(\d+)\s*kg", mission_name):
                match = re.search(r"(\d+)\s*kg", mission_name)
                if "more than" in mission_name or "heavier" in mission_name:
                    data["target_missions"].append(("weight_greater", int(match.group(1))))
                    continue
                elif "less than" in mission_name or "lower" in mission_name:
                    data["target_missions"].append(("weight_lower", int(match.group(1))))
                    continue

            # Type count
            if "type" in mission_name and "mono" in mission_name:
                data["target_missions"].append(("type_count", 1))
                continue
            elif "type" in mission_name and "dual" in mission_name:
                data["target_missions"].append(("type_count", 2))
                continue

            # Type
            for pokemon_type in pokemon_types:
                if pokemon_type in mission_name:
                    data["target_missions"].append(("type", pokemon_type))
                    break

    return data


def handle_pokedex_data(server_data):
    """Treats fetched pokedex data"""

    if server_data is None:
        return None

    data = {
        "dex": [{"name": item["name"], "pokedex_id": item["pokedexId"]} for item in server_data["dex"]],
        "total_count": server_data["totalPkm"],
        "total_progress": server_data["progress"],
        "spawn_count": server_data["catchablePkm"],
        "spawn_progress": server_data["catchableProgress"],
    }

    return data


def handle_pokemon_data(server_data):
    """Treats fetched pokemon data"""

    if server_data is None:
        return None

    def get_pokemon_types(type1, type2):
        types = [type1, type2]
        return list(filter(lambda x: x != "none" and x is not None, types))

    data = {
        "pokedex_id": server_data["content"]["pokedex_id"],
        "name": server_data["content"]["name"],
        "weight": server_data["content"]["weight"],
        "types": get_pokemon_types(server_data["content"]["type1"], server_data["content"]["type2"]),
        "tier": server_data["content"]["tier"],
        "base_stats": sum(server_data["content"]["base_stats"].values()),
        "base_hp": server_data["content"]["base_stats"]["hp"],
        "base_speed": server_data["content"]["base_stats"]["speed"],
    }

    return data


def handle_last_spawn_data(server_data):
    """Treats fetched last spawn data"""

    if server_data is None:
        return None

    data = {
        "spawn_date": parser.isoparse(server_data["event_time"]).astimezone(tz.tzlocal()),
        "pokedex_id": server_data["pokedex_id"],
        "isEventSpawn": server_data.get("isEventSpawn", False)
    }

    return data

# Re-attach static method if needed by calling code
PokemonData.get_last_spawn_data = staticmethod(get_last_spawn_data_static)
