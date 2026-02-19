from datetime import datetime, timedelta
from json import dumps
import asyncio

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal

from src.GuiPages.alert import AlertPage
from src.GuiPages.config import ConfigPage
from src.GuiPages.home import HomePage
from src.LogicConfig.index import LogicConfig
from src.LogicDealer.index import LogicDealer
from src.PokemonData.index import PokemonData
from src.TwitchLoginManager.index import TwitchLoginManager
from src.TwitchSocketManager.index import TwitchSocketManager
from src.helpers.PokeJwt import PokeJwt
from src.helpers.UserData import UserData

from assets.const.bot_status import BOT_STATUS
from assets.const.connection_status import CONNECTION_STATUS


class MainApplication(QWidget):
    """
    This is our application core using asyncio.
    It coordinates app actions, and connects different classes.
    """
    
    pokemon_data_updated_signal = pyqtSignal()

    def __init__(self, program_path):

        super().__init__()
        
        self.pokemon_data_updated_signal.connect(self._on_pokemon_data_updated_slot)

        self._program_path = program_path

        self._connection_status = CONNECTION_STATUS["STARTING"]
        self._bot_status = BOT_STATUS["ACTIVE"]

        self.LogicConfig = LogicConfig(
            self._program_path,
            self.update_language_callback,
            self.update_channel_callback
        )
        self.LogicConfig.theme_callback = self.update_theme_callback

        self.TwitchLoginManager = TwitchLoginManager(
            self._program_path,
            self.twitch_connection_status_callback,
            self.twitch_update_jwt_callback,
            self.twitch_login_success_callback,
            self.twitch_connection_timeout_callback,
            self.twitch_error_callback,
        )

        self.TwitchSocketManager = TwitchSocketManager(
            self.chat_connection_callback,
            self.chat_disconnection_callback,
            self.chat_connection_error_callback,
            self.poke_spawn_callback,
        )

        self.PokemonData = PokemonData(
            self.poke_data_update_callback,
            self.poke_data_error_callback,
            self.TwitchLoginManager.browser_service
        )

        self.LogicDealer = LogicDealer(
            self.LogicConfig,
            self.PokemonData,
            self.last_spawn_data_callback,
            self.TwitchSocketManager.send_chat_message
        )

        self.HomePage = HomePage(
            self._program_path,
            self.on_home_load_callback,
            self.on_home_close_callback,
            self.change_bot_status,
            self.open_config,
            self.request_twitch_login, 
            self.twitch_logout,
        )

        self.ConfigPage = ConfigPage(
            self._program_path,
            self.on_config_load_callback,
            self.save_config_callback
        )

        self.AlertPage = AlertPage(
            self._program_path,
            self.on_alert_load_callback,
        )

        self._user_data = None
        self._poke_jwt = None

        self._time_out_error = None
        self._socket_error = None

        self._main_task = None
        self._is_running = True

        self.init_gui()

    def init_gui(self):
        """Initializes app home page"""
        self.HomePage.init()

    async def run(self):
        """Main async entry point called by main.py"""
        self._is_running = True
        self._main_task = asyncio.create_task(self._main_loop())
        
        while self._is_running:
             await asyncio.sleep(1)

    async def _main_loop(self):
        """Main loop that replaces Worker"""
        while self._is_running:
            await self._main_tick()
            await asyncio.sleep(1)

    async def _main_tick(self):
        """Single iteration of the main loop logic"""
        if self.connection_status == CONNECTION_STATUS["DISCONNECTED"] or \
                self.connection_status == CONNECTION_STATUS["ERROR"] or \
                self.bot_status == BOT_STATUS["STOPPED"]:
            return

        if self.connection_status == CONNECTION_STATUS["STARTING"]:
            self._get_twitch_oauth()

        elif self.connection_status == CONNECTION_STATUS["CONNECTED"]:

            if self.poke_jwt is None or self.poke_jwt.exp - datetime.now() < timedelta(minutes=10):
                self._get_twitch_jwt()
                return

            if not self.TwitchSocketManager.connected:
                self._connect_chat(self.LogicConfig.channel)
                return

            self.LogicDealer.spawn_routine(self.bot_status)

        elif self.connection_status == CONNECTION_STATUS["TIMEOUT"]:
            if datetime.now() - self._time_out_error > timedelta(seconds=15):
                self._get_twitch_oauth()

        elif self.connection_status == CONNECTION_STATUS["SOCKET_ERROR"]:
            if datetime.now() - self._socket_error > timedelta(seconds=15):
                self._connect_chat(self.LogicConfig.channel)

    def request_twitch_login(self):
        print("GUI: User requested Login. Setting status to LOADING.")
        self._get_twitch_oauth()

    def _get_twitch_oauth(self):
        if self.bot_status != BOT_STATUS["STOPPED"]:
            self.connection_status = CONNECTION_STATUS["LOADING"]
            self.TwitchLoginManager.start_get_twitch_oauth_process()

    def _get_twitch_jwt(self):
        if self.bot_status != BOT_STATUS["STOPPED"] and self.connection_status != CONNECTION_STATUS["GETTING_JWT"]:
            self.connection_status = CONNECTION_STATUS["GETTING_JWT"]
            self.TwitchLoginManager.get_twitch_jwt()

    def _connect_chat(self, channel):
        if self.user_data is not None and self.bot_status != BOT_STATUS["STOPPED"]:
            self.connection_status = CONNECTION_STATUS["CONNECTING_SOCKET"]
            self.TwitchSocketManager.connect(self.user_data, channel)

    def _get_pokemon_user_data(self):
        if self.bot_status != BOT_STATUS["STOPPED"]:
            self.PokemonData.update_data()


    def change_bot_status(self, new_status):
        if new_status == BOT_STATUS["STOPPED"]:
            self.TwitchSocketManager.disconnect()

        if self.bot_status == BOT_STATUS["STOPPED"] and new_status != BOT_STATUS["STOPPED"]:
            self.connection_status = CONNECTION_STATUS["STARTING"]

        self.bot_status = new_status

    def open_config(self):
        self.ConfigPage.open()

    def twitch_logout(self):
        self.connection_status = CONNECTION_STATUS["DISCONNECTED"]
        
        asyncio.create_task(self.TwitchLoginManager.clear_cookies())
        self.user_data = None
        self.poke_jwt = None

        self.TwitchSocketManager.disconnect()

        self.HomePage.reset_pokemon_data()


    def update_language_callback(self, new_language):
        self.HomePage.update_language(new_language)
        self.AlertPage.update_language(new_language)

    def update_theme_callback(self, new_theme):
        self.HomePage.update_theme(new_theme)

    def update_channel_callback(self, new_channel):
        if self.connection_status == CONNECTION_STATUS["CONNECTED"]:
            self.connection_status = CONNECTION_STATUS["CONNECTING_SOCKET"]
            self.TwitchSocketManager.disconnect()
            self._connect_chat(new_channel)

        self.HomePage.update_joined_chat(new_channel)

    def twitch_connection_status_callback(self, connection_data):
        if not connection_data["username"]:
            print("Login Error: Missing username.")
            self.connection_status = CONNECTION_STATUS["DISCONNECTED"]
            self.user_data = None
            asyncio.create_task(self.TwitchLoginManager.clear_cookies())
            self.TwitchSocketManager.disconnect()
        else:
            self.user_data = UserData(connection_data)
            self._get_twitch_jwt()

    def twitch_update_jwt_callback(self, encoded_jwt):
        if self.connection_status == CONNECTION_STATUS["ERROR"]:
            return

        if not encoded_jwt:
            self.poke_jwt = None
            return
        else:
            self.poke_jwt = PokeJwt(encoded_jwt)
            self._get_pokemon_user_data()

            if self.connection_status in [CONNECTION_STATUS["GETTING_JWT"], CONNECTION_STATUS["LOADING"], CONNECTION_STATUS["DISCONNECTED"]]:
                if not self.TwitchSocketManager.connected:
                    self._connect_chat(self.LogicConfig.channel)
                else:
                    self.connection_status = CONNECTION_STATUS["CONNECTED"]

    def twitch_login_success_callback(self):
        self.connection_status = CONNECTION_STATUS["LOADING"]

    def twitch_connection_timeout_callback(self):
        if self.connection_status == CONNECTION_STATUS["LOADING"]:
            self.user_data = None
            self.poke_jwt = None
        elif self.connection_status == CONNECTION_STATUS["GETTING_JWT"]:
            self.poke_jwt = None

        self._time_out_error = datetime.now()
        self.connection_status = CONNECTION_STATUS["TIMEOUT"]

    def twitch_error_callback(self):
        self.user_data = None
        self.poke_jwt = None
        asyncio.create_task(self.TwitchLoginManager.clear_cookies())
        
        self.bot_status = BOT_STATUS["STOPPED"]
        self.connection_status = CONNECTION_STATUS["ERROR"]

    def chat_connection_callback(self):
        if self.connection_status == CONNECTION_STATUS["CONNECTING_SOCKET"]:
            self.connection_status = CONNECTION_STATUS["CONNECTED"]

    def chat_disconnection_callback(self):
        if self.connection_status != CONNECTION_STATUS["DISCONNECTED"] and self.bot_status != BOT_STATUS["STOPPED"]:
            self._socket_error = datetime.now()
            self.connection_status = CONNECTION_STATUS["SOCKET_ERROR"]

    def chat_connection_error_callback(self):
        self._socket_error = datetime.now()
        self.connection_status = CONNECTION_STATUS["SOCKET_ERROR"]

    def poke_spawn_callback(self, chat_message):
        if self.bot_status != BOT_STATUS["STOPPED"]:
            self.LogicDealer.investigate_last_spawn(self.bot_status, chat_message)

    def poke_data_update_callback(self):
        self.pokemon_data_updated_signal.emit()

    def _on_pokemon_data_updated_slot(self):
        print("Pokemon data updated (Main Thread).")
        
        self.HomePage.update_pokemon_data(dumps({
            "captured": self.PokemonData.captured,
            "pokedex": self.PokemonData.pokedex,
            "inventory": self.PokemonData.inventory,
            "missions": self.PokemonData.missions,
        }))

    def poke_data_error_callback(self, error_code=None):
        print(f"Error fetching Pokemon Data (Code: {error_code}).")
        
        if error_code == -24 or error_code == 401:
             print("Token Expired or Invalid. Triggering Refresh...")
             if self.connection_status != CONNECTION_STATUS["GETTING_JWT"]:
                 self._get_twitch_jwt()
             else:
                 print("Already refreshing JWT. Ignoring error.")

    def last_spawn_data_callback(self, spawn_data):
        self.HomePage.update_last_spawn(dumps(spawn_data))

    def on_home_load_callback(self):
        self.HomePage.update_connection_status(self.connection_status)
        self.HomePage.update_bot_status(self.bot_status)
        self.HomePage.update_language(self.LogicConfig.language)
        self.HomePage.update_theme(self.LogicConfig.theme)
        self.HomePage.update_joined_chat(self.LogicConfig.channel)
        if self.user_data is not None:
            self.HomePage.update_username(self.user_data.username)

    def on_home_close_callback(self):
        self._is_running = False
        if self._main_task:
             self._main_task.cancel()

        self.HomePage.close()
        self.ConfigPage.close()
        self.AlertPage.close()
        self.TwitchLoginManager.close_web()
        self.TwitchSocketManager.disconnect()

    def on_alert_load_callback(self):
        self.AlertPage.update_language(self.LogicConfig.language)

    def on_config_load_callback(self):
        self.ConfigPage.update_config_data(dumps({
            "language": self.LogicConfig.language,
            "theme": self.LogicConfig.theme,
            "channel": self.LogicConfig.channel,
            "shop": self.LogicConfig.shop,
            "catch": self.LogicConfig.catch,
            "stats_balls": self.LogicConfig.stats_balls,
        }))

    def save_config_callback(self, new_config):
        self.LogicConfig.update(new_config)
        self.on_config_load_callback()

    @property
    def connection_status(self):
        return self._connection_status

    @connection_status.setter
    def connection_status(self, new_value):
        if self._connection_status != new_value:
            self._connection_status = new_value
            self.HomePage.update_connection_status(new_value)

    @property
    def bot_status(self):
        return self._bot_status

    @bot_status.setter
    def bot_status(self, new_value):
        if self._bot_status != new_value:
            self._bot_status = new_value
            self.HomePage.update_bot_status(new_value)

    @property
    def user_data(self):
        return self._user_data

    @user_data.setter
    def user_data(self, new_value):
        if self._user_data != new_value:
            self._user_data = new_value

            if new_value is not None:
                self.HomePage.update_username(new_value.username)

    @property
    def poke_jwt(self):
        return self._poke_jwt

    @poke_jwt.setter
    def poke_jwt(self, new_value):
        if self._poke_jwt != new_value:
            self._poke_jwt = new_value
            self.PokemonData.update_poke_jwt(new_value)
