# Teacher Bot — Discord Server Stats

A Discord bot that silently collects your server's message history and surfaces stats, trends, and semantic analysis through a local web portal. No slash commands. No messages posted to Discord. Just data.

## How it works

1. Start the bot — it connects to Discord and backfills all message history it hasn't seen yet
2. Open `http://localhost:8080` in your browser
3. Explore stats by server, channel, or user; run semantic analysis; download transcripts
4. Stop the bot whenever — next run picks up where it left off

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com/) installed and running locally (for semantic analysis)
- A Discord bot token (see setup below)

## Installation

```bash
git clone https://github.com/nivag1288/Teacher_Bot
cd Teacher_Bot
pip install -r requirements.txt
cp .env.example .env
# edit .env with your credentials
```

## Discord Bot Setup

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) and create a new application
2. Go to **Bot** → add a Bot user → copy the token → paste into `.env` as `DISCORD_TOKEN`
3. Under **Bot → Privileged Gateway Intents**, enable:
   - **Server Members Intent** — required to track join/leave events
   - **Message Content Intent** — required to read message text for transcripts and analysis
4. Go to **OAuth2 → URL Generator** and select:
   - Scopes: `bot`
   - Bot permissions:
     - `Read Messages / View Channels`
     - `Read Message History`
     - `View Audit Log` ← required for member join/leave history
5. Copy the generated URL, open it in a browser, and invite the bot to your server
6. Right-click your server icon → **Copy Server ID** → paste into `.env` as `DISCORD_GUILD_ID`

## Configuration

Copy `.env.example` to `.env` and fill in each value:

| Variable | Description | Default |
|---|---|---|
| `DISCORD_TOKEN` | Bot token from Discord Developer Portal | required |
| `DISCORD_GUILD_ID` | Numeric ID of your server | required |
| `OLLAMA_HOST` | Ollama API host | `localhost:11434` |
| `OLLAMA_MODEL` | Model to use for analysis | `llama3.2` |
| `DB_PATH` | Path to SQLite database file | `data/stats.db` |
| `WEB_PORT` | Port for the web portal | `8080` |

## Running

```bash
python bot/main.py
```

The bot connects to Discord, backfills any new message history, and starts the web portal at `http://localhost:8080`. A banner in the portal shows backfill progress. Stop with `Ctrl+C`.

## Running Tests

```bash
pytest tests/ --cov=. --cov-report=term-missing --cov-config=.coveragerc
```

## Known Limitations

- **Audit log retention**: Discord only stores the audit log for 45 days. Member join/leave history older than that is not recoverable.
- **Reply references**: `reply_to_author_id` is populated only when Discord resolves the referenced message during backfill. Older or deleted referenced messages may be unresolvable.
- **Initial backfill time**: Large servers with many channels and messages will take several minutes on first run. The web portal shows a live progress banner while backfill runs.
