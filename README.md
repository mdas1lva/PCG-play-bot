# PCG-play-bot v2

## Description
This is a modern, asynchronous tool developed to auto-play **Pokemon Community Game (PCG)** on Twitch while you work. Built with `playwright` and `qasync`, it stays completely hidden while efficiently tracking and completing PCG interactions for you. 

This major milestone update (v2) features:
- **Catppuccin UI:** A brand new, sleek configuration window with built-in theme pickers.
- **Asynchronous Core:** CPU consumption drastically lowered by switching to Playwright Async API, HTTPX, and native Python `asyncio`.
- **v2 API Support:** The bot automatically retrieves and manages your PCG `JWT` tokens to interact directly with the new PCG API v2 endpoints.
- **Point-Based Smart Catching:** Completely overhauled catching logic. The bot will intelligently throw Pokéballs based on a custom-weighted point system mapping tier lists to your available inventory resources.
- **Twitch Integration Base:** Supports automatic connection and authentication via a hidden Playwright Chrome instance (Currently tested extensively with Google login).

## Warning
This program uses unconventional methods to extract authorization tokens from Twitch and connect to PCG. Twitch and PCG may consider these practices strictly illegal and/or abusive, and your account may be subject to punishment and banning. **Use it at your own risk.**

Using this program on an account where there is already a chat bot connected may result in strange behavior resulting in account suspicion.

## Installation

### Prerequisites
Make sure you have Google Chrome installed, as the Playwright browser automation relies on it.
Additionally, you need a `.env` file containing your channel information before first launch.

### Compilation from source
The recommended way to run the bot is from source using Python 3.8+ or 3.12+.

1. Clone repo from GitHub:
   ```bash
   git clone https://github.com/PcgPlayBot/PCG-play-bot.git
   ```
   
2. Navigate to project source:
    ```bash
    cd PCG-play-bot
    ```
   
3. Install the requirements:
    ```bash
    pip install -r requirements.txt
    ```

4. Install Playwright binaries for the browser auto-login:
    ```bash
    playwright install chromium
    ```

5. Run the application:
    ```bash
    python main.py
    ```

## How to Login
Since the v2 refactor, the bot handles login uniquely:
1. When you launch the bot, a Chromium browser window will spawn alongside the UI.
2. The bot will prompt you to log into Twitch. Note: *This is currently only fully tested using Google Single Sign-on for Twitch.*
3. The bot tells you to navigate yourself to the channel you specified in the configuration.
4. The bot captures your Twitch tokens and requests a signing key for the **PCG API v2**.
5. This browser instance stays visible while the bot runs seamlessly in the background.

## Contributing 
This program was initially developed during vacations and is continuously evolving. Feel free to submit pull requests and contribute to the open-source code!

## Disclaimer
The author has no responsibility for the usage of this program. Usage of PCG-play-bot is at your own risk, and the author provides no warranty or guarantee of its performance or effects.

The author disclaims any responsibility for any consequences, including but not limited to penalties or account suspensions, resulting from the use of this bot.

### Contact
pcgplaybot@gmail.com
