
# StreamSpy Discord-Bot

Ein Discord-Bot, der Twitch-Streams überwacht und automatisch im gewünschten Discord-Channel benachrichtigt, sobald ein Streamer live geht.  
Der Bot unterstützt mehrere Server (Guilds), speichert Konfigurationen persistent und erlaubt individuelle Nachrichtenvorlagen.

---

## Features

- Benachrichtigung, wenn ein Twitch-Streamer live geht.
- Pro Discord-Server konfigurierbar (Channel-Auswahl, Streamer-Liste).
- Unterstützung für mehrere Streamer pro Server (bis zu 50 pro Guild).
- Anpassbare Nachrichtenvorlagen mit Platzhaltern (`{streamer}`, `{title}`, `{viewers}`, `{url}`).
- Persistente Speicherung der Konfiguration in `data/streamspy.json`.
- Automatisches Logging:
  - Nachrichten-Logs pro Server.
  - Memberlisten-Logs pro Server.
  - Rotierende Logdateien (`streamspy.log`).

---

## Voraussetzungen

- Python **3.9+** installiert.
- [Discord Bot](https://discord.com/developers/applications) erstellt (inkl. Bot-Token).
- [Twitch Developer Application](https://dev.twitch.tv/console/apps) erstellt (für Client-ID und Client-Secret).
- Discord-Intents aktiviert:
  - **SERVER MEMBERS INTENT**
  - **MESSAGE CONTENT INTENT**

---

## Installation & Setup

### 1. Repository klonen oder Dateien ablegen
```bash
git clone https://github.com/dein-user/streamspy-bot.git
cd streamspy-bot
````

### 2. Virtuelle Umgebung erstellen (empfohlen)

```bash
python3 -m venv venv
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows PowerShell
```

### 3. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 4. Umgebungsvariablen setzen

#### Option A: `.env`-Datei (empfohlen)

Erstelle eine Datei `.env` im Projektordner mit folgendem Inhalt:

```env
DISCORD_TOKEN=dein_discord_token
DISCORD_CHANNEL_ID=123456789012345678
TWITCH_CLIENT_ID=deine_twitch_client_id
TWITCH_CLIENT_SECRET=dein_twitch_client_secret
TWITCH_USER_LOGIN=streamer_login
POLL_SECONDS=60
STREAMSPY_DEBUG=0
```

Nutze dann ein Tool wie [python-dotenv](https://pypi.org/project/python-dotenv/), oder exportiere Variablen selbst.

#### Option B: Direkt in der Shell setzen

Linux/macOS:

```bash
export DISCORD_TOKEN="dein_discord_token"
export TWITCH_CLIENT_ID="deine_twitch_client_id"
export TWITCH_CLIENT_SECRET="dein_twitch_client_secret"
python3 Bot.py
```

Windows PowerShell:

```powershell
$env:DISCORD_TOKEN="dein_discord_token"
$env:TWITCH_CLIENT_ID="deine_twitch_client_id"
$env:TWITCH_CLIENT_SECRET="dein_twitch_client_secret"
& C:/path/to/python.exe Bot.py
```

ich empfehle hier aber dies alles in der Bot.py Datei einzustellen.

---

## Start des Bots

```bash
python3 Bot.py
```

Wenn alles korrekt eingerichtet ist, erscheint im Log:

```
YYYY-MM-DD HH:MM:SS INFO: Bot ready: StreamSpy#1234
```

---

## Slash-Befehle (`/streamspy ...`)

### `/streamspy select`

Setzt den aktuellen Channel als Ziel für Benachrichtigungen.

### `/streamspy addstreamer <streamer> [message]`

Fügt einen Streamer hinzu. Optional mit eigener Nachrichtenvorlage.
Platzhalter:

* `{streamer}` → Name des Streamers
* `{title}` → Titel des Streams
* `{viewers}` → Zuschauerzahl
* `{url}` → Stream-URL

### `/streamspy removestreamer <streamer>`

Entfernt einen Streamer aus der Überwachung.

### `/streamspy list`

Listet alle überwachten Streamer des Servers.

### `/streamspy settemplate <streamer> <template>`

Setzt die Nachrichtenvorlage für einen Streamer neu.

### `/streamspy twitchstatus`

Zeigt den aktuellen Status des Standard-Streamers (`TWITCH_USER_LOGIN`).

---

## Beispiel für Benachrichtigung

```text
:red_circle: ninja ist jetzt live auf Twitch!
Pro-Level Gaming
Zuschauer: 15342
https://twitch.tv/ninja
```

---

## Verzeichnisse & Dateien

* **`streamspy.log`** → Rotierende Logs für Aktivitäten des Bots.
* **`data/streamspy.json`** → Persistente Speicherung (Channel & Streamer pro Guild).
* **`Message Logs/`** → Nachrichtenlogs pro Server.
* **`Member Lists/`** → Vollständige Memberlisten der Server.

---

## Deployment-Hinweise

* Für dauerhaften Betrieb empfiehlt sich **tmux**, **screen** oder **systemd service** unter Linux.

* Beispiel systemd Service Unit:

  ```ini
  [Unit]
  Description=StreamSpy Discord Bot
  After=network.target

  [Service]
  Type=simple
  WorkingDirectory=/home/user/streamspy-bot
  ExecStart=/home/user/streamspy-bot/venv/bin/python Bot.py
  Restart=always
  Environment="DISCORD_TOKEN=dein_discord_token"
  Environment="TWITCH_CLIENT_ID=deine_twitch_client_id"
  Environment="TWITCH_CLIENT_SECRET=dein_twitch_client_secret"

  [Install]
  WantedBy=multi-user.target
  ```

* Logs findest du in `streamspy.log` sowie in den Unterordnern `Message Logs` und `Member Lists`.

---

## Lizenz

Siehe [LICENSE](LICENSE)

