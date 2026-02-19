import re
import asyncio
from datetime import datetime
import json
from dateutil import parser, tz
from src.helpers.SignatureHelper import SignatureHelper
import httpx # For the fallback/external GET requests
import sys

from assets.const.urls import POKEMON_EXTENSION_URL, POKEMON_SPAWN_URL

class PokemonData:
    """
    This class handles fetching user pokemon data asynchronously.
    """
    def __init__(self, poke_data_update_callback, poke_data_error_callback, browser_service):

        self._poke_jwt = None
        self._browser_service = browser_service
        self._jwt_refreshed = asyncio.Event()
        self._jwt_refreshed.set() # Unblocked initially

        self._data_update_callback = poke_data_update_callback
        self._data_error_callback = poke_data_error_callback

        self._update_task = None
        
        # Register Passive Listener (now an async callback internally)
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
        """Updates JWT"""
        self._poke_jwt = new_value
        if new_value:
             self._jwt_refreshed.set()

    def update_data(self):
        """Spawns an async task to fetch user's pokemon data"""
        if self._poke_jwt is not None:
             self._update_task = asyncio.create_task(self._update_data_async())

    async def _update_data_async(self):
        print("Updating pokemon data (Async Fetch)...")

        captured_raw = await self._fetch_api_data("pokemon/v2/")
        captured = await handle_captured_data(captured_raw, self.get_pokemon_data, self._buddy_details_cache)
        self._captured = captured if captured is not None else self._captured

        inventory_raw = await self._fetch_api_data("inventory/v3/")
        inventory = handle_inventory_data(inventory_raw)
        self._inventory = inventory if inventory is not None else self._inventory

        missions_raw = await self._fetch_api_data("mission/v2/")
        missions = handle_missions_data(missions_raw)
        self._missions = missions if missions is not None else self._missions

        pokedex_raw = await self._fetch_api_data("pokedex/v2/")
        pokedex = handle_pokedex_data(pokedex_raw)
        self._pokedex = pokedex if pokedex is not None else self._pokedex

        self._data_update_callback()

    async def _fetch_api_data(self, data_type, custom_headers=None, retry_count=0):
        """Fetches data using async browser fetch."""
        if self._poke_jwt is None:
            return None

        auth_val = self._poke_jwt.jwt
        
        if not data_type.endswith("/") and "?" not in data_type:
            data_type += "/"

        url = f"{POKEMON_EXTENSION_URL}/{data_type}"

        if custom_headers:
            headers = custom_headers
        else:
            try:
                 user_id = self._poke_jwt.user_id
                 headers = SignatureHelper.get_pcg_headers(str(user_id), url, auth_val)
            except Exception as e:
                 print(f"Error generating signature for {url}: {e}")
                 headers = {
                    "Authorization": auth_val,
                    "Accept": "application/json, text/plain, */*",
                    "clientVersion": "1.4.3.1"
                 }

        try:
            response = await self._browser_service.fetch_in_extension_frame(url, headers=headers)
            
            if response and response["status"] == 200:
                try:
                    return json.loads(response["text"])
                except:
                    print(f"Error parsing JSON from {url}")
                    return None
            else:
                code = response["status"] if response else "Unknown"
                text = response["text"] if response else ""
                
                if code == 400 and '"error":-20' in text.replace(" ", ""):
                    print(f"Verified: Signature required for {data_type}.")
                    return None

                if code == 400 and '"error":-24' in text.replace(" ", ""):
                     print("Pokemon API: Token Expired. Triggering Refresh...")
                     
                     if retry_count == 0:
                         self._jwt_refreshed.clear()
                         self._data_error_callback(-24)
                         
                         print("Waiting for JWT Refresh (Max 60s)...")
                         try:
                             await asyncio.wait_for(self._jwt_refreshed.wait(), timeout=60.0)
                             print("JWT Refreshed! Retrying request...")
                             return await self._fetch_api_data(data_type, custom_headers=None, retry_count=1)
                         except asyncio.TimeoutError:
                             print("Wait for JWT Refresh timed out.")
                             return None
                     else:
                         print("Retry failed for Token Expiration. Giving up.")
                         return None
                    
                print(f"Pokemon request error for {data_type}. Status: {code}")
                return None
                
        except Exception as e:
            if "Event loop" not in str(e) and "stopped" not in str(e):
                print(f"Pokemon API Request Error: {e}", file=sys.stderr, flush=True)
            self._data_error_callback(None)
            return None

    async def _on_browser_response(self, url, json_data):
        """Callback for passive data sniffing from browser."""
        if "pokemon/v2" in url:
            print("Captured Passive: Pokemon List")
            captured = await handle_captured_data(json_data, self.get_pokemon_data, self._buddy_details_cache)
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

    async def get_pokemon_data(self, pokedex_id):
        """Fetches specific pokemon data (Async)"""
        # 1. Local Cache
        if self._captured and "all_pokemon_raw" in self._captured:
            for p in self._captured["all_pokemon_raw"]:
                if p["pokedexId"] == pokedex_id:
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
                        break 
                    
        # 2. Fetch
        try:
             url_endpoint = f"pokedex/info/v2/?pokedex_id={pokedex_id}"
             data = await self._fetch_api_data(url_endpoint)
             if data: return handle_pokemon_data(data)
        except Exception as e:
             print(f"Error fetching signed data: {e}")
             
        print(f"Critical Error: Could not fetch details for ID {pokedex_id}.")
        return None

    def check_inventory(self, item_name):
        return any(item.get("sprite_name") == item_name for item in self.inventory["items"])

    @property
    def captured(self): return self._captured
    @property
    def inventory(self): return self._inventory
    @property
    def missions(self): return self._missions
    @property
    def pokedex(self): return self._pokedex


async def get_last_spawn_data_static():
    """Fetches last spawn data from API server via Async Httpx"""
    try:
        async with httpx.AsyncClient() as client:
             response = await client.get(POKEMON_SPAWN_URL, timeout=10.0)
             if response.status_code == 200:
                 return handle_last_spawn_data(response.json())
             else:
                 print(f"Spawn data request error. Status: {response.status_code}")
                 return None
    except Exception as e:
        print(f"Spawn data error: {e}")
        return None

PokemonData.get_last_spawn_data = staticmethod(get_last_spawn_data_static)

# Helpers
async def handle_captured_data(server_data, get_pokemon_data, buddy_cache=None):
    if server_data is None: return None

    data = {
        "total_count": len(server_data["allPokemon"]),
        "unique_captured_ids": [],
        "unique_count": 0,
        "shiny_count": 0,
        "buddy_types": [],
        "all_pokemon_raw": server_data["allPokemon"]
    }

    for pokemon in server_data["allPokemon"]:
        if pokemon["pokedexId"] not in data["unique_captured_ids"]:
            data["unique_captured_ids"].append(pokemon["pokedexId"])
            data["unique_count"] += 1
        if pokemon["isShiny"]:
            data["shiny_count"] += 1

        if pokemon.get("isBuddy", False):
            buddy_data = None
            if buddy_cache and buddy_cache.get("pokedex_id") == pokemon["pokedexId"] and buddy_cache.get("data"):
                 buddy_data = buddy_cache["data"]
            else:
                 # Fetch logic is now async
                 buddy_data = await get_pokemon_data(pokemon["pokedexId"])
                 if buddy_cache is not None and buddy_data is not None:
                     buddy_cache["pokedex_id"] = pokemon["pokedexId"]
                     buddy_cache["data"] = buddy_data

            if buddy_data is not None:
                data["buddy_types"] = buddy_data["types"]

    return data


def handle_inventory_data(server_data):
    if server_data is None: return None
    return {
        "cash": server_data["cash"],
        "items": [
            {"name": item["name"], "amount": item["amount"], "sprite_name": item.get("sprite_name", item.get("name", "Unknown"))}
            for item in server_data["allItems"]
        ]
    }


def handle_missions_data(server_data):
    if server_data is None: return None
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
        "grass", "flying", "dark", "electric", "psychic", "ice", "bug", "fairy"
    ]

    for mission in data["missions"]:
        mission_name = mission["name"].lower()
        if "catch" in mission_name and "miss" not in mission_name and mission["progress"] < mission["goal"]:
            if "tier" in mission_name:
                match = re.search(r"tier\s+(\w)", mission_name)
                if match:
                    data["target_missions"].append(("tier", match.group(1)))
                    continue
            if "bst" in mission_name:
                match = re.findall(r"\d+", mission_name)
                if len(match) > 0:
                    if "greater" in mission_name or "higher" in mission_name:
                        data["target_missions"].append(("bst_greater", int(match[1])))
                        continue
                    elif "lower" in mission_name:
                        data["target_missions"].append(("bst_lower", int(match[1])))
                        continue
            if re.search(r"(\d+)\s*kg", mission_name):
                match = re.search(r"(\d+)\s*kg", mission_name)
                if match:
                    if "more than" in mission_name or "heavier" in mission_name:
                        data["target_missions"].append(("weight_greater", int(match.group(1))))
                        continue
                    elif "less than" in mission_name or "lower" in mission_name:
                        data["target_missions"].append(("weight_lower", int(match.group(1))))
                        continue
            if "type" in mission_name and "mono" in mission_name:
                data["target_missions"].append(("type_count", 1))
                continue
            elif "type" in mission_name and "dual" in mission_name:
                data["target_missions"].append(("type_count", 2))
                continue
            for pokemon_type in pokemon_types:
                if pokemon_type in mission_name:
                    data["target_missions"].append(("type", pokemon_type))
                    break

    return data


def handle_pokedex_data(server_data):
    if server_data is None: return None
    return {
        "dex": [{"name": item["name"], "pokedex_id": item["pokedexId"]} for item in server_data["dex"]],
        "total_count": server_data["totalPkm"],
        "total_progress": server_data["progress"],
        "spawn_count": server_data["catchablePkm"],
        "spawn_progress": server_data["catchableProgress"],
    }


def handle_pokemon_data(server_data):
    if server_data is None: return None
    def get_pokemon_types(type1, type2):
        types = [type1, type2]
        return list(filter(lambda x: x != "none" and x is not None, types))

    return {
        "pokedex_id": server_data["content"]["pokedex_id"],
        "name": server_data["content"]["name"],
        "weight": server_data["content"]["weight"],
        "types": get_pokemon_types(server_data["content"]["type1"], server_data["content"]["type2"]),
        "tier": server_data["content"]["tier"],
        "base_stats": sum(server_data["content"]["base_stats"].values()),
        "base_hp": server_data["content"]["base_stats"]["hp"],
        "base_speed": server_data["content"]["base_stats"]["speed"],
    }


def handle_last_spawn_data(server_data):
    if server_data is None: return None
    return {
        "spawn_date": parser.isoparse(server_data["event_time"]).astimezone(tz.tzlocal()),
        "pokedex_id": server_data["pokedex_id"],
        "isEventSpawn": server_data.get("isEventSpawn", False)
    }
