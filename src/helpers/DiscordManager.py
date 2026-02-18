import requests
from threading import Thread

class DiscordManager:
    """
    Manages Discord Webhook notifications for high-tier Pokemon spawns.
    """
    def __init__(self, config_manager):
        self.config_manager = config_manager

    @property
    def enabled(self):
        return self.config_manager.discord_enabled

    @property
    def webhook_url(self):
        return self.config_manager.discord_webhook_url
    
    @property
    def ping_user(self):
        return self.config_manager.discord_ping_user

    def send_spawn_notification(self, pokemon_data):
        """
        Sends a rich embed notification for a spawned Pokemon.
        """
        if not self.enabled or not self.webhook_url:
            return

        # Run in a separate thread to avoid blocking game logic
        Thread(target=self._send_notification_thread, args=(pokemon_data,)).start()

    def _send_notification_thread(self, p_data):
        try:
            # Check Tier (We only want S and A notifications as per request, but let's be flexible in code)
            tier = p_data.get("tier", "Unknown")
            
            # Basic Color Coding
            color = 0x7289DA # Blurple default
            if tier == "S":
                color = 0xFFD700 # Gold
            elif tier == "A":
                color = 0x800080 # Purple
            elif tier == "B":
                color = 0x0000FF # Blue
            
            # Construct Embed
            embed = {
                "title": f"Wild {p_data['name']} Appeared!",
                "description": f"**Tier:** {tier}\n**IV:** {p_data.get('iv', '?')}%",
                "color": color,
                "thumbnail": {
                    "url": p_data.get("img", "")
                },
                "fields": [
                    {
                        "name": "Stats",
                        "value": "\n".join([f"**{k.capitalize()}:** {v}" for k, v in p_data.get("stats", {}).items()]),
                        "inline": True
                    },
                    {
                        "name": "Types",
                        "value": ", ".join(p_data.get("types", [])),
                        "inline": True
                    }
                ],
                "footer": {
                    "text": f"ID: {p_data.get('id', '???')}"
                }
            }

            payload = {
                "embeds": [embed]
            }

            if self.ping_user:
                payload["content"] = "@everyone A high tier pokemon has spawned!"

            response = requests.post(self.webhook_url, json=payload)
            if response.status_code not in [200, 204]:
                print(f"Discord Webhook Failed: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"Error sending Discord notification: {e}")
