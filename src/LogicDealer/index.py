from datetime import datetime, timedelta
from math import floor
from random import randint
import asyncio

from dateutil import tz

from assets.const.bot_status import BOT_STATUS

from src.helpers.DiscordManager import DiscordManager


class LogicDealer:
    # ...

    def __init__(self, logic_config, pokemon_data, last_spawn_data_callback, socket_send_chat_message):

        self._logic_config = logic_config
        self._pokemon_data = pokemon_data
        self._spawn_data_callback = last_spawn_data_callback
        self._socket_send_chat_message = socket_send_chat_message
        
        self.discord_manager = DiscordManager(logic_config)

        self._handle_spawn_task = None
        self._last_spawn = None

        self._sleep_before_talking = randint(0, 30)
        self._last_chat_interaction = None
    
    # ...

    async def _handle_spawn(self, spawn_data, should_capture):
        """Handle a pokemon spawn after spawn data has been set"""

        pokemon_data = spawn_data["pokemon_data"]

        if pokemon_data["tier"] != "S" and self._check_spawn_is_mission(pokemon_data):
            pokemon_data["tier"] = "M"

        if pokemon_data["pokedex_id"] not in self._pokemon_data.captured["unique_captured_ids"]:
            if not self._logic_config.catch.get("treat_uncapt_as_capt", False):
                pokemon_data["tier"] = f"uncapt_{pokemon_data['tier']}"

        chosen_ball = await self._choose_capture_ball(pokemon_data) if should_capture else None

        if chosen_ball is not None:

            print(f"A wild {pokemon_data['name']} (Tier: {pokemon_data['tier']}) (Types: {', '.join([t for t in pokemon_data['types'] if t])}) appeared! Using {chosen_ball} to attempt capture.")

            await sleep_before_catch(spawn_data["datetime"], chosen_ball)
            self._send_catch_command(chosen_ball)

            if spawn_data["is_pcg_spawn"]:
                self._last_spawn["attempt_catch"] = True

        else:
            print(f"Wild {pokemon_data['name']} (Tier: {pokemon_data['tier']}) (Types: {', '.join([t for t in pokemon_data['types'] if t])}) appeared, but no ball was chosen (or capture disabled).")

        if self.last_spawn is not None:
            self._last_spawn["updated_data_after_spawn"] = False

    def _send_chat_message(self, command):
        """Uses socket function to send a message to chat"""

        self._last_chat_interaction = datetime.now()

        print(f"Sending chat message: '{command}'")
        self._socket_send_chat_message(command)

    def _send_catch_command(self, ball):
        """Sends the catch command with chosen ball"""

        if ball == "poke_ball":
             self._send_chat_message("!pokecatch")
             return

        ball_name = ball.replace("_", " ")
        self._send_chat_message(f"!pokecatch {ball_name}")

    def spawn_routine(self, bot_status):
        """Main routine to be run after a spawn. It listens to new spawns, updates pokemon data and keeps chat active"""

        if self.last_spawn is None:
            self.investigate_last_spawn(bot_status)
            return

        next_spawn_date: datetime = self.last_spawn["datetime"] + timedelta(minutes=15)
        time_to_next_spawn = next_spawn_date - datetime.now(tz=tz.tzlocal())

        if time_to_next_spawn < timedelta(minutes=13, seconds=20) and not self.last_spawn["updated_data_after_spawn"]:
            self._last_spawn["updated_data_after_spawn"] = True
            self._pokemon_data.update_data()

    def investigate_last_spawn(self, bot_status, chat_message=None):
        """Investigates the last spawn"""

        if self._handle_spawn_task is None or self._handle_spawn_task.done():
            self._handle_spawn_task = asyncio.create_task(self._investigate_last_spawn(bot_status, chat_message))

    async def _investigate_last_spawn(self, bot_status, chat_message):
        """Investigates the last spawn in task. It not found on server data, fire handle from chat"""

        spawn_data = await self._pokemon_data.get_last_spawn_data()

        started_time = datetime.now()
        while len(self._pokemon_data.pokedex["dex"]) == 0 and datetime.now() - started_time < timedelta(seconds=20):
            await asyncio.sleep(1)

        should_capture = bot_status == BOT_STATUS["ACTIVE"]

        if spawn_data is not None and \
                (self.last_spawn is None or spawn_data["spawn_date"] != self.last_spawn["datetime"]):
            await self._handle_spawn_from_server(spawn_data, should_capture)
        elif chat_message is not None and should_capture:
            await self._handle_spawn_from_chat(chat_message, should_capture)

    async def _handle_spawn_from_server(self, last_spawn_data, should_capture):
        """Handles spawn using data from pokemon API"""

        print("Handling spawn from server data.")

        pokemon_data = await self._pokemon_data.get_pokemon_data(last_spawn_data["pokedex_id"])

        if pokemon_data is None:
            print(f"Error: Could not retrieve data for pokemon ID {last_spawn_data['pokedex_id']}. Spawn ignored.")
            return

        self._last_spawn = {
            "pokedex_id": pokemon_data["pokedex_id"],
            "name": pokemon_data["name"],
            "datetime": last_spawn_data["spawn_date"],
            "attempt_catch": False,
            "updated_data_after_spawn": False,
            "checked_pokemon": False,
            "talked_in_chat_after_spawn": False,
        }

        spawn_data = {
            "datetime": last_spawn_data["spawn_date"],
            "is_pcg_spawn": True,
            "pokemon_data": pokemon_data,
        }

        self._spawn_data_callback({
            "name": self.last_spawn["name"],
            "datetime": self.last_spawn["datetime"].isoformat()
        })
        self._sleep_before_talking = randint(0, 30)

        if (datetime.now(tz=tz.tzlocal()) - spawn_data["datetime"]).total_seconds() < 90:
            await self._handle_spawn(spawn_data, should_capture)

    async def _handle_spawn_from_chat(self, chat_message, should_capture):
        """Handles spawn using message from chat"""

        print("Handling spawn from chat message.")

        id_from_message = get_pokemon_id_from_chat_message(chat_message, self._pokemon_data.pokedex["dex"])
        pokemon_data = await self._pokemon_data.get_pokemon_data(id_from_message) if id_from_message is not None else None

        if pokemon_data is None:
            return

        spawn_data = {
            "datetime": datetime.now(tz=tz.tzlocal()),
            "is_pcg_spawn": False,
            "pokemon_data": pokemon_data,
        }

        await self._handle_spawn(spawn_data, should_capture)


    def _check_spawn_is_mission(self, pokemon_data):
        """Checks if a pokemon spawn is required for any mission"""

        for mission in self._pokemon_data.missions["target_missions"]:

            if mission[0] == "tier" and pokemon_data["tier"] == mission[1]:
                return True

            elif mission[0] == "bst_greater" and pokemon_data["base_stats"] > mission[1]:
                return True

            elif mission[0] == "bst_lower" and pokemon_data["base_stats"] < mission[1]:
                return True

            elif mission[0] == "weight_greater" and pokemon_data["weight"] > mission[1]:
                return True

            elif mission[0] == "weight_lower" and pokemon_data["weight"] < mission[1]:
                return True

            elif mission[0] == "type_count" and len(pokemon_data["types"]) == mission[1]:
                return True

            elif mission[0] == "type":
                for pokemon_type in pokemon_data["types"]:
                    if pokemon_type == mission[1]:
                        return True
                        
        return False

    async def _choose_capture_ball(self, pokemon_data):
        """Chooses the best poke ball based on catch rate and economic value"""

        available_balls = []
        
        if "poke_ball" in self._logic_config.catch[pokemon_data["tier"]]:
            available_balls.append("poke_ball")
        if "great_ball" in self._logic_config.catch[pokemon_data["tier"]]:
            available_balls.append("great_ball")
        if "ultra_ball" in self._logic_config.catch[pokemon_data["tier"]]:
            available_balls.append("ultra_ball")
        if "master_ball" in self._logic_config.catch[pokemon_data["tier"]]:
            available_balls.append("master_ball")
            
        inventory_items = [item["sprite_name"] for item in self._pokemon_data.inventory["items"]]
        
        tier_config = self._logic_config.catch[pokemon_data["tier"]]
        
        best_ball = None
        best_score = -1
        
        def can_use_ball(ball_name):
            
            core_tier = pokemon_data["tier"].replace("uncapt_", "")
            
            high_tier_balls = [
                "ultra_ball", "quick_ball", "timer_ball", 
                "heavy_ball", "feather_ball", "net_ball", "phantom_ball", 
                "night_ball", "frozen_ball", "cipher_ball", "magnet_ball", 
                "fantasy_ball", "geo_ball", "heal_ball", "fast_ball"
            ]
            
            if ball_name in high_tier_balls:
                if core_tier not in ["S", "A", "B"]:
                    return False, "restricted_tier_low"

            if core_tier == "C":
                if ball_name == "great_ball":
                    if self._pokemon_data.inventory["cash"] < 2000:
                        return False, "restricted_cash_c"
                elif ball_name != "poke_ball" and ball_name != "premier_ball":
                     return False, "restricted_tier_c"

            if ball_name in inventory_items:
                return True, "inventory"
            
            if ball_name in ["poke_ball", "great_ball", "ultra_ball"]:
                cash = self._pokemon_data.inventory["cash"]
                
                if ball_name == "great_ball":
                    limit = 2000 if core_tier == "C" else 900
                    if cash <= limit:
                         return False, "restricted_cash"
                        
                if ball_name == "ultra_ball":
                    if core_tier not in ["S", "A"]:
                         return False, "restricted_tier"
                    if cash <= 1500: 
                         return False, "restricted_cash"
                
                if ball_name in self._logic_config.shop:
                     return True, "shop"
                     
            return False, "unavailable"

        from assets.const.pokemon_data import POKE_BALLS_LIST
        
        candidate_balls = []

        for ball_key in tier_config:
            
            actual_balls_to_check = []
            
            if ball_key == "types_ball":
                actual_balls_to_check.extend(["net_ball", "phantom_ball", "night_ball", "frozen_ball", "cipher_ball", "magnet_ball", "fantasy_ball", "geo_ball"])
            elif ball_key == "stats_ball":
                actual_balls_to_check.extend(["heavy_ball", "feather_ball", "heal_ball", "fast_ball"])
            elif ball_key == "timers_ball":
                actual_balls_to_check.extend(["quick_ball", "timer_ball"])
            else:
                actual_balls_to_check.append(ball_key)
                
            for ball in actual_balls_to_check:
                is_available, source = can_use_ball(ball)
                if is_available:
                    score = self._calculate_ball_score(ball, pokemon_data)
                    
                    candidate_balls.append({
                        "ball": ball,
                        "score": score,
                        "source": source
                    })

        def get_ball_cost(ball_name):
            if ball_name == "poke_ball": return 300
            if ball_name == "great_ball": return 600
            if ball_name == "ultra_ball": return 1000
            return 2000
        
        candidate_balls.sort(key=lambda x: (x["score"], x["source"] == "inventory", -get_ball_cost(x["ball"])), reverse=True)
        
        if not candidate_balls:
            return None
            
        best_choice = candidate_balls[0]
        ball = best_choice["ball"]
        
        if best_choice["source"] == "shop":
            if await self.handle_purchase_balls(ball):
                return ball
            else:
                candidate_balls.pop(0)
                if candidate_balls:
                    return candidate_balls[0]["ball"]
                return None
                
        return ball

    def _calculate_ball_score(self, ball, pokemon_data):
        """Calculates a catch score (0-100+) for a given ball and pokemon"""
        
        score = 0
        
        if ball == "poke_ball": score = 30
        elif ball == "great_ball": score = 55
        elif ball == "ultra_ball": score = 80
        elif ball == "master_ball": score = 1000
        
        elif ball == "premier_ball": score = 30 
        elif ball == "cherish_ball": score = 30 
        elif ball == "great_cherish_ball": score = 55
        elif ball == "ultra_cherish_ball": score = 80
        
        elif ball == "heavy_ball":
            w = pokemon_data.get("weight", 0)
            if w > 400: score = 80 
            elif w > 200: score = 50
            else: score = 20
            
        elif ball == "feather_ball":
            w = pokemon_data.get("weight", 0)
            if w < 50: score = 80 
            elif w < 100: score = 50
            else: score = 20
        
        elif ball == "net_ball":
            if "water" in pokemon_data["types"] or "bug" in pokemon_data["types"]:
                score = 70
            else: score = 30
            
        elif ball == "phantom_ball":
            score = 80 if "ghost" in pokemon_data["types"] else 30
            
        elif ball == "night_ball":
            score = 80 if "dark" in pokemon_data["types"] else 30
            
        elif ball == "frozen_ball":
            score = 80 if "ice" in pokemon_data["types"] else 30
            
        elif ball == "cipher_ball":
            score = 70 if "poison" in pokemon_data["types"] or "psychic" in pokemon_data["types"] else 30
            
        elif ball == "magnet_ball":
            score = 80 if "electric" in pokemon_data["types"] or "steel" in pokemon_data["types"] else 30

        elif ball == "fantasy_ball":
            score = 80 if "dragon" in pokemon_data["types"] or "fairy" in pokemon_data["types"] else 30

        elif ball == "geo_ball":
            score = 80 if "rock" in pokemon_data["types"] or "ground" in pokemon_data["types"] else 30
            
        elif ball == "heal_ball":
             score = 80 if pokemon_data.get("base_hp", 0) >= self._logic_config.stats_balls["heal_ball"] else 20
             
        elif ball == "fast_ball":
             score = 80 if pokemon_data.get("base_speed", 0) > self._logic_config.stats_balls["fast_ball"] else 20

        elif ball == "quick_ball":
            score = 90
            
        elif ball == "timer_ball":
            score = 90 
            
        elif ball == "repeat_ball":
            if "uncapt" not in pokemon_data["tier"]:
                score = 75
            else:
                score = 30
                
        elif ball == "friend_ball" or ball == "buddy_ball":
            score = 30
            for t in pokemon_data["types"]:
                if t in self._pokemon_data.captured["buddy_types"]:
                    score = 70
                    break

        elif ball == "level_ball":
            score = 50
            
        elif ball == "stone_ball":
            score = 50

        elif ball == "clone_ball":
            score = 30
            if pokemon_data["tier"] in ["S", "A"]:
                score += 10 
        
        return score

    async def handle_purchase_balls(self, ball):
        """Purchase balls based on user's config"""

        shop_config = self._logic_config.shop.get(ball, {})
        if not shop_config: return False
        
        purchased = False

        await asyncio.sleep(randint(5, 10))  

        if not shop_config.get("buy_on_missing", False):
            purchased = False

        elif self._pokemon_data.inventory["cash"] > shop_config.get("buy_ten", 999999):
            self._send_chat_message(f"!pokeshop {ball.replace('_', ' ')} 10")
            purchased = True

        elif self._pokemon_data.inventory["cash"] > shop_config.get("buy_one", 999999):
            self._send_chat_message(f"!pokeshop {ball.replace('_', ' ')}")
            purchased = True

        if purchased:
            await asyncio.sleep(6)
            
        return purchased

    @property
    def last_spawn(self):
        return self._last_spawn


def get_pokemon_id_from_chat_message(chat_message, pokedex):
    """"Finds out which pokemon spawned from a chat message"""

    names_matches = []
    for entry in pokedex:
        if entry["name"].lower() in chat_message.lower():
            names_matches.append(entry["pokedex_id"])

    return names_matches[-1] if len(names_matches) > 0 else None


async def sleep_before_catch(spawn_date, chosen_ball):
    """"Sleeps before attempting catch. This is used to time throws and randomize bot behaviour"""

    if chosen_ball == "quick_ball":
        print("Quick Ball selected: Skipping sleep to maximize catch rate.")
        return

    sleep_time = 0

    if chosen_ball == "timer_ball":
        desired_throw_time: datetime = spawn_date + timedelta(minutes=1, seconds=20)
        remaining_time = (desired_throw_time - datetime.now(tz=tz.tzlocal())).total_seconds()

        if floor(remaining_time) > 0:
            sleep_time = floor(remaining_time)
            print(f"Timer Ball selected: Waiting {sleep_time}s to maximize effectiveness.")

    else:
        max_wait_time: datetime = spawn_date + timedelta(minutes=1)
        remaining_time = (max_wait_time - datetime.now(tz=tz.tzlocal())).total_seconds()

        if floor(remaining_time) > 0:
            sleep_time = randint(0, floor(remaining_time))

    if sleep_time > 0:
        print(f"Sleeping {sleep_time} seconds before attempting catch.")
        await asyncio.sleep(sleep_time)
