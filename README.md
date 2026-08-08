# Zakmolanitech Bot

A simple Telegram giveaway bot that posts a giveaway message with an inline "Join" button, records participants to an SQLite database, and allows the admin to pick a winner.

## Features
- Admin-only commands to start/stop giveaways and pick a winner
- Inline "Join Giveaway" button for participants
- SQLite persistence (giveaways.db) for giveaways and participants
- A tiny Flask server to keep the service alive (port 10000)
- Useful commands: `/startgiveaway`, `/stopgiveaway`, `/pickwinner`, `/myid`

## Requirements
- Python 3.9+
- Packages:
  - python-telegram-bot (v20+)
  - Flask
  - python-dotenv

Example quick install:
```bash
python -m pip install "python-telegram-bot>=20.0" Flask python-dotenv
```

## Environment variables
Create a `.env` file or set these in your host (Render, etc.):

```
TOKEN=<your-telegram-bot-token>
CHANNEL_ID=<channel-or-chat-id>     # e.g. -1001234567890 or @yourchannel
ADMIN_ID=<your-telegram-user-id>    # numeric user id (used for admin-only commands)
```

You can get your Telegram ID via `/myid` after starting the bot.

## Running locally
1. Ensure env vars are set (.env or environment).
2. Run:
```bash
python zakmolanitech_bot.py
```
- The Flask server listens on port 10000 to keep the service alive for hosting platforms.

## Deployment notes
- On Render (or similar), create a Web service, add the env vars, and set the start/command to run the bot (e.g. `python zakmolanitech_bot.py`). Use manual deploy after pushing changes.
- Ensure the bot has been started by users who will receive DMs (otherwise direct messages may fail).

## Database
- The bot creates `giveaways.db` automatically in the working directory.
- Tables: `giveaways` and `participants`.

## Troubleshooting
- If DM fails, ask users to start a chat with the bot first.
- Keep your `TOKEN` secret — do not commit it to the repo.

If you want, I can add a `requirements.txt` file as well (recommended).