import asyncio
import websockets
from datetime import datetime
from assets.const.pokemon_data import POKEMON_BOT_NAME
from assets.const.urls import TWITCH_CHAT_SERVER, TWITCH_CHAT_PORT

class TwitchSocketManager:
    """
    Manages websocket connection to Twitch IRC.
    Uses async/await for non-blocking I/O.
    """
    def __init__(self,
                 chat_connection_callback,
                 chat_disconnection_callback,
                 chat_connection_error_callback,
                 poke_spawn_callback,
                 ):

        self._connection_callback = chat_connection_callback
        self._disconnection_callback = chat_disconnection_callback
        self._error_callback = chat_connection_error_callback
        self._poke_spawn_callback = poke_spawn_callback

        self._ws = None
        self._connected = False
        self._connected_channel = None
        self._listener_task = None

    def connect(self, user_data, channel_name):
        """Initiates websocket connection."""
        print("Connecting socket (async).")
        asyncio.create_task(self._connect_async(user_data, channel_name))

    async def _connect_async(self, user_data, channel_name):
        uri = "wss://irc-ws.chat.twitch.tv:443"
        try:
            self._ws = await websockets.connect(uri)
            
            # Send Auth
            await self._ws.send(f"PASS {user_data.oauth}")
            await self._ws.send(f"NICK {user_data.username}")
            await self._ws.send(f"JOIN #{channel_name}")
            
            # Wait for successful connection (End of /NAMES)
            loading = True
            
            try:
                # Wait up to 30 seconds for auth
                while loading:
                    msg = await asyncio.wait_for(self._ws.recv(), timeout=30.0)
                    for line in msg.split('\r\n'):
                        if "End of /NAMES list" in line:
                            loading = False
                            break
                        elif "Login authentication failed" in line:
                            print("Twitch authentication failed.")
                            await self._on_disconnect_async()
                            return
            except asyncio.TimeoutError:
                 print("Twitch auth timeout.")
                 await self._on_disconnect_async()
                 return
                 
            # Connected!
            self._connected = True
            self._connected_channel = channel_name
            self._on_connect()
            
            # Start listener loop
            self._listener_task = asyncio.create_task(self._receive_messages())

        except Exception as error:
            print("Socket connection error:\n", error)
            # Call error callback via event loop or directly if threadsafe
            self._error_callback()

    def _on_connect(self):
        print("Socket connected.")
        self._connection_callback()

    def disconnect(self):
        """Closes the websocket connection."""
        if self._connected:
             asyncio.create_task(self._on_disconnect_async())

    async def _on_disconnect_async(self):
        """Async disconnection logic."""
        self._connected = False
        self._connected_channel = None
        if self._listener_task:
             self._listener_task.cancel()
             self._listener_task = None
             
        if self._ws:
             try:
                 await self._ws.close()
             except: pass
             self._ws = None
             
        self._disconnection_callback()

    async def _receive_messages(self):
        """Main listening loop."""
        try:
            while self._connected and self._ws:
                msg = await self._ws.recv()
                
                for line in msg.split('\r\n'):
                    if not line: continue
                    
                    # Ping pong
                    if line.startswith('PING'):
                        await self._ws.send('PONG :tmi.twitch.tv')
                        continue
                        
                    if 'PRIVMSG' in line and POKEMON_BOT_NAME in line:
                        parts = line.split(':', 2)
                        try:
                            sender = parts[1].split('!', 1)[0]
                            content = parts[2]
                            self._process_message(sender, content)
                        except IndexError:
                            print("Index Error:", line)
                            
        except websockets.ConnectionClosed:
             print("Websocket connection closed by server.")
             await self._on_disconnect_async()
        except asyncio.CancelledError:
             pass
        except Exception as error:
             print("Socket error: ", error)
             await self._on_disconnect_async()

    def _process_message(self, sender, message):
        """Processes PCG spawn messages."""
        if sender != POKEMON_BOT_NAME:
            return

        if "!pokecatch" in message and "90" in message:
            self._poke_spawn_callback(message)

    def send_chat_message(self, message):
        """Sends a message in chat. Fires and forgets task."""
        if self._connected and self._connected_channel is not None and self._ws:
             asyncio.create_task(self._send_chat_message_async(message))
             
    async def _send_chat_message_async(self, message):
        try:
            message_temp = f'PRIVMSG #{self._connected_channel} :{message}'
            await self._ws.send(message_temp)
        except Exception as e:
            print(f"Failed to send message: {e}")

    @property
    def connected(self):
        return self._connected
