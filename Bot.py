import os
import asyncio
import json
from pathlib import Path
import logging
import aiohttp
import time
import sys
import discord
from discord.ext import commands, tasks
from discord import app_commands

#!/usr/bin/env python3
# Bot.py
# Discord-Bot: Benachrichtigt in einem bestimmten Channel, wenn ein Twitch-Streamer live geht.
# Konfiguration über Umgebungsvariablen oder direkt hier eintragen.



logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
# Add rotating file handler for persistent logs
try:
    from logging.handlers import RotatingFileHandler
    fh = RotatingFileHandler('streamspy.log', maxBytes=5_000_000, backupCount=3, encoding='utf-8')
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(fh)
except Exception:
    logging.exception("Could not set up file logging")

# Konfiguration (ersetzten oder via Umgebungsvariablen setzen)
# Read Discord token from environment variable. Do NOT hardcode your token here.
DISCORD_TOKEN = "MTQwNjg4Nzg5NDc5NDI0NDE4OA.Ge7XRk.ohOTi5Nxr3HRemgQ5dKxYHWkzYD7i4aDEQTw54"
DISCORD_CHANNEL_ID = int(os.environ.get("DISCORD_CHANNEL_ID") or "123456789012345678")
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID") or "YOUR_TWITCH_CLIENT_ID"
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET") or "YOUR_TWITCH_CLIENT_SECRET"
TWITCH_USER_LOGIN = os.environ.get("TWITCH_USER_LOGIN") or "streamer_login"  # z.B. "ninja"
POLL_SECONDS = int(os.environ.get("POLL_SECONDS") or "60")  # Abfrage-Intervall in Sekunden

intents = discord.Intents.default()
# discord.py requires a command_prefix for commands.Bot; use a harmless default
bot = commands.Bot(command_prefix="!", intents=intents)
streamspy = app_commands.Group(name="streamspy", description="StreamSpy Befehle")

# Per-guild selected channel for notifications: {guild_id: channel_id}
SELECTED_CHANNELS = {}

# Per-guild trackers: {guild_id: {streamer_login_lower: message_template}}
TRACKERS = {}

# Per-guild live state: {guild_id: {streamer_login_lower: bool}}
LIVE_STATE = {}

# Default message template (can use {streamer}, {title}, {viewers}, {url})
DEFAULT_TEMPLATE = ":red_circle: {streamer} ist jetzt live auf Twitch!\n{title}\nZuschauer: {viewers}\n{url}"

# Persistence file
DATA_DIR = Path.cwd() / "data"
DATA_FILE = DATA_DIR / "streamspy.json"
TRACKER_LIMIT = 50


def _ensure_data_dir():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        logging.exception("Could not create data directory")


def load_state():
    _ensure_data_dir()
    if not DATA_FILE.exists():
        return
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        SELECTED_CHANNELS.clear()
        for k, v in data.get("selected", {}).items():
            SELECTED_CHANNELS[int(k)] = int(v)
        TRACKERS.clear()
        for k, v in data.get("trackers", {}).items():
            TRACKERS[int(k)] = {s: t for s, t in v.items()}
        logging.info("Loaded streamspy state: %s guilds", len(TRACKERS))
    except Exception:
        logging.exception("Failed to load state from %s", DATA_FILE)


def save_state():
    _ensure_data_dir()
    try:
        data = {
            "selected": {str(k): v for k, v in SELECTED_CHANNELS.items()},
            "trackers": {str(k): v for k, v in TRACKERS.items()},
        }
        with DATA_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logging.info("Saved streamspy state: %s guilds", len(TRACKERS))
    except Exception:
        logging.exception("Failed to save state to %s", DATA_FILE)


def _format_console_line(guild_id: int, guild_name: str, channel_id: int, streamer: str, title: str, viewers, url: str) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    return f"[{ts}] [LIVE] Guild={guild_name}({guild_id}) Channel={channel_id} Streamer={streamer} Viewers={viewers} Title={title} URL={url}"


def console_live_log(guild: discord.Guild, channel_id: int, streamer: str, title: str, viewers, url: str):
    try:
        line = _format_console_line(guild.id if guild else 0, guild.name if guild else "DM", channel_id, streamer, title, viewers, url)
        # Print to stdout for an easy live log view and also to logging
        print(line)
        logging.info(line)
    except Exception:
        logging.exception("Fehler beim Schreiben des Live-Logs")

class TwitchAPI:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expires_at = 0

    async def ensure_token(self, session: aiohttp.ClientSession):
        if self.token and time.time() < self.token_expires_at - 30:
            return
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        # Retry on transient network errors
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                async with session.post(url, params=params) as resp:
                    data = await resp.json()
                    if resp.status != 200:
                        logging.error("Failed to get Twitch token (status %s): %s", resp.status, data)
                        raise RuntimeError("Twitch token error")
                    self.token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self.token_expires_at = time.time() + expires_in
                    return
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                logging.warning("Attempt %s/%s: network error while fetching Twitch token: %s", attempt, max_attempts, e)
                if attempt == max_attempts:
                    logging.exception("Exceeded attempts fetching Twitch token")
                    raise
                await asyncio.sleep(2 ** attempt)

    async def get_stream(self, session: aiohttp.ClientSession, user_login: str):
        # Ensure token (may raise)
        await self.ensure_token(session)
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.token}",
        }
        url = "https://api.twitch.tv/helix/streams"
        params = {"user_login": user_login}
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 401 and attempt == 1:
                        # Token expired/invalid -> refresh and retry
                        await self.ensure_token(session)
                        headers["Authorization"] = f"Bearer {self.token}"
                        continue
                    if resp.status != 200:
                        text = await resp.text()
                        logging.error("Twitch streams error (status %s): %s", resp.status, text)
                        return None
                    j = await resp.json()
                    return j.get("data", [])
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                logging.warning("Attempt %s/%s: network error while fetching stream for %s: %s", attempt, max_attempts, user_login, e)
                if attempt == max_attempts:
                    logging.exception("Failed to fetch stream data for %s after retries", user_login)
                    return None
                await asyncio.sleep(1 * attempt)


twitch = TwitchAPI(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET)

# (on_ready is defined later after command registration)

@bot.event
async def on_close():
    if hasattr(bot, "http_session"):
        await bot.http_session.close()

@tasks.loop(seconds=POLL_SECONDS)
async def check_stream():
    try:
        session: aiohttp.ClientSession = bot.http_session
        # Prüfe alle Gilden und deren konfigurierten Streamer
        for guild in bot.guilds:
            gid = guild.id
            trackers = TRACKERS.get(gid)
            if not trackers:
                continue
            sel_chan_id = SELECTED_CHANNELS.get(gid)
            if not sel_chan_id:
                logging.info("Keine ausgewählten Channel für Guild %s, überspringe Tracker", gid)
                continue
            channel = bot.get_channel(sel_chan_id)
            if channel is None:
                logging.warning("Ausgewählter Channel %s in Guild %s nicht gefunden", sel_chan_id, gid)
                continue
            # Go through each tracked streamer for this guild
            guild_state = LIVE_STATE.setdefault(gid, {})
            for streamer, template in list(trackers.items()):
                try:
                    data = await twitch.get_stream(session, streamer)
                    is_live = bool(data and len(data) > 0)
                    prev = guild_state.get(streamer, False)
                    if is_live and not prev:
                        stream = data[0]
                        title = stream.get("title", "Kein Titel")
                        viewers = stream.get("viewer_count", "unbekannt")
                        url = f"https://twitch.tv/{streamer}"
                        # Format the message template
                        try:
                            msg = (template or DEFAULT_TEMPLATE).format(streamer=streamer, title=title, viewers=viewers, url=url)
                        except Exception:
                            msg = DEFAULT_TEMPLATE.format(streamer=streamer, title=title, viewers=viewers, url=url)
                        await channel.send(msg)
                        logging.info("Notified guild %s about %s live", gid, streamer)
                        # Console live log
                        try:
                            guild_obj = discord.utils.get(bot.guilds, id=gid)
                            console_live_log(guild_obj, sel_chan_id, streamer, title, viewers, url)
                        except Exception:
                            logging.exception("Fehler beim Schreiben des Console-Live-Logs")
                    guild_state[streamer] = is_live
                except Exception as e:
                    logging.exception("Fehler beim Prüfen von %s in Guild %s: %s", streamer, gid, e)
    except Exception as e:
        logging.exception("Fehler beim Prüfen des Streams: %s", e)

@check_stream.before_loop
async def before_check():
    await bot.wait_until_ready()


@streamspy.command(name="twitchstatus", description="Gibt aktuellen Stream-Status aus.")
async def twitchstatus(interaction: discord.Interaction):
    session: aiohttp.ClientSession = bot.http_session
    data = await twitch.get_stream(session, TWITCH_USER_LOGIN)
    if data and len(data) > 0:
        stream = data[0]
        title = stream.get("title", "Kein Titel")
        viewers = stream.get("viewer_count", "unbekannt")
        await interaction.response.send_message(f"{TWITCH_USER_LOGIN} ist live: {title} ({viewers} Zuschauer)", ephemeral=True)
    else:
        await interaction.response.send_message(f"{TWITCH_USER_LOGIN} ist derzeit offline.", ephemeral=True)


@streamspy.command(name="select", description="Setzt den Channel für StreamSpy-Benachrichtigungen.")
async def select_channel(interaction: discord.Interaction):
    gid = interaction.guild.id if interaction.guild else None
    if gid is None:
        return await interaction.response.send_message("Nur in einer Gilde nutzbar.", ephemeral=True)
    SELECTED_CHANNELS[gid] = interaction.channel.id
    await interaction.response.send_message(f"StreamSpy Channel gesetzt: <#{interaction.channel.id}>", ephemeral=True)


@streamspy.command(name="addstreamer", description="Fügt einen Streamer hinzu (Platzhalter: {streamer},{title},{viewers},{url})")
@app_commands.describe(streamer="Twitch-Benutzername des Streamers", message="Nachrichtenvorlage (optional)")
async def add_streamer(interaction: discord.Interaction, streamer: str, message: str = None):
    gid = interaction.guild.id if interaction.guild else None
    if gid is None:
        return await interaction.response.send_message("Nur in einer Gilde nutzbar.", ephemeral=True)
    # Ensure a channel is selected
    if gid not in SELECTED_CHANNELS:
        return await interaction.response.send_message("Bitte zuerst mit /streamspy select einen Channel wählen.", ephemeral=True)
    s = streamer.lower()
    trackers = TRACKERS.setdefault(gid, {})
    if len(trackers) >= TRACKER_LIMIT:
        return await interaction.response.send_message(f"Maximale Anzahl von Trackern ({TRACKER_LIMIT}) erreicht.", ephemeral=True)
    trackers[s] = message or DEFAULT_TEMPLATE
    # Ensure live state entry exists
    LIVE_STATE.setdefault(gid, {})[s] = False
    save_state()
    await interaction.response.send_message(f"Streamer **{streamer}** hinzugefügt. Benachrichtigungen gehen an <#{SELECTED_CHANNELS[gid]}>.", ephemeral=True)


@streamspy.command(name="list", description="Listet die überwachten Streamer in dieser Gilde auf.")
async def list_streamers(interaction: discord.Interaction):
    gid = interaction.guild.id if interaction.guild else None
    if gid is None:
        return await interaction.response.send_message("Nur in einer Gilde nutzbar.", ephemeral=True)
    trackers = TRACKERS.get(gid) or {}
    if not trackers:
        return await interaction.response.send_message("Keine Streamer konfiguriert.", ephemeral=True)
    lines = [f"- {s}: {t[:80]}" for s, t in trackers.items()]
    txt = "\n".join(lines)
    await interaction.response.send_message(f"Überwachte Streamer:\n{txt}", ephemeral=True)


@streamspy.command(name="removestreamer", description="Entfernt einen überwachten Streamer.")
@app_commands.describe(streamer="Twitch-Benutzername des zu entfernenden Streamers")
async def remove_streamer(interaction: discord.Interaction, streamer: str):
    gid = interaction.guild.id if interaction.guild else None
    if gid is None:
        return await interaction.response.send_message("Nur in einer Gilde nutzbar.", ephemeral=True)
    s = streamer.lower()
    trackers = TRACKERS.get(gid)
    if not trackers or s not in trackers:
        return await interaction.response.send_message("Streamer nicht gefunden.", ephemeral=True)
    trackers.pop(s, None)
    LIVE_STATE.get(gid, {}).pop(s, None)
    save_state()
    await interaction.response.send_message(f"Streamer **{streamer}** entfernt.", ephemeral=True)


@streamspy.command(name="settemplate", description="Setzt die Nachrichtenvorlage für einen überwachten Streamer.")
@app_commands.describe(streamer="Twitch-Benutzername", template="Neue Nachrichtenvorlage (Platzhalter: {streamer},{title},{viewers},{url})")
async def set_template(interaction: discord.Interaction, streamer: str, template: str):
    gid = interaction.guild.id if interaction.guild else None
    if gid is None:
        return await interaction.response.send_message("Nur in einer Gilde nutzbar.", ephemeral=True)
    s = streamer.lower()
    trackers = TRACKERS.get(gid)
    if not trackers or s not in trackers:
        return await interaction.response.send_message("Streamer nicht gefunden.", ephemeral=True)
    trackers[s] = template or DEFAULT_TEMPLATE
    save_state()
    await interaction.response.send_message(f"Vorlage für **{streamer}** gesetzt.", ephemeral=True)


# Slash-Commands registrieren und synchronisieren
@bot.event
async def on_ready():
    logging.info("Bot ready: %s", bot.user)
    # Load persisted state (selected channels and trackers) on startup
    load_state()
    # Use trust_env=True so aiohttp respects system proxy settings (HTTP_PROXY/HTTPS_PROXY)
    # and set a reasonable timeout to fail fast on network issues.
    bot.http_session = aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=30))
    bot._stream_was_live = False
    bot.tree.add_command(streamspy)
    await bot.tree.sync()
    check_stream.start()

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable is not set.\n\nSet it in PowerShell like this:\n")
        print("# PowerShell:\n$env:DISCORD_TOKEN = 'your_token_here'\n& C:/path/to/python.exe Bot.py\n")
        print("# Or temporarily for a single command (PowerShell):\n$Env:DISCORD_TOKEN='your_token_here'; & C:/path/to/python.exe Bot.py\n")
        print("# On Linux/macOS:\nexport DISCORD_TOKEN='your_token_here'\npython3 Bot.py\n")
        sys.exit(1)
    try:
        bot.run(DISCORD_TOKEN)
    finally:
        if "bot" in globals() and hasattr(bot, "http_session"):

            asyncio.get_event_loop().run_until_complete(bot.http_session.close())
