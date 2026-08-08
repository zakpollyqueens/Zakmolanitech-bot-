import os
import asyncio
import threading
import logging
import sqlite3
import random
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

# Validate environment variables
required_vars = ['TOKEN', 'CHANNEL_ID', 'ADMIN_ID']
for var in required_vars:
    if var not in os.environ:
        raise ValueError(f"Missing required environment variable: {var}")

TOKEN = os.environ['TOKEN']
CHANNEL_ID = os.environ['CHANNEL_ID']
# Ensure ADMIN_ID is an int when possible
try:
    ADMIN_ID = int(os.environ['ADMIN_ID'])
except Exception:
    ADMIN_ID = os.environ['ADMIN_ID']

# Store giveaway data in memory (with database backup for persistence)
giveaways = {}             # mapping message_id -> [user_id, ...]
active_giveaway_id = None  # Track the current giveaway message ID

# Database setup for persistence
DB_PATH = 'giveaways.db'


def init_database():
    """Initialize SQLite database for giveaway persistence."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS giveaways (
            message_id INTEGER PRIMARY KEY,
            channel_id TEXT,
            created_at TIMESTAMP,
            participants TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giveaway_id INTEGER,
            user_id INTEGER,
            username TEXT,
            joined_at TIMESTAMP,
            FOREIGN KEY (giveaway_id) REFERENCES giveaways(message_id)
        )
    ''')
    conn.commit()
    conn.close()


def save_giveaway_to_db(msg_id, channel_id):
    """Save giveaway to database."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO giveaways (message_id, channel_id, created_at, participants)
                VALUES (?, ?, ?, ?)
            ''', (msg_id, channel_id, datetime.now(), ''))
            conn.commit()
        logging.info(f"Giveaway {msg_id} saved to database")
    except Exception as e:
        logging.error(f"Failed to save giveaway to database: {e}")


def add_participant_to_db(msg_id, user_id, username):
    """Add participant to database."""
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO participants (giveaway_id, user_id, username, joined_at)
                VALUES (?, ?, ?, ?)
            ''', (msg_id, user_id, username, datetime.now()))
            conn.commit()
        logging.info(f"Participant {user_id} added to giveaway {msg_id}")
    except Exception as e:
        logging.error(f"Failed to add participant to database: {e}")


def load_giveaways_from_db():
    """Load active giveaways from database on startup."""
    global giveaways, active_giveaway_id
    try:
        with sqlite3.connect(DB_PATH, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT message_id, channel_id FROM giveaways')
            rows = cursor.fetchall()
            for msg_id, channel_id in rows:
                cursor.execute('SELECT user_id FROM participants WHERE giveaway_id = ?', (msg_id,))
                participants = [row[0] for row in cursor.fetchall()]
                giveaways[msg_id] = participants
                active_giveaway_id = msg_id  # Restore the last giveaway
            logging.info(f"Loaded {len(giveaways)} giveaways from database")
    except Exception as e:
        logging.error(f"Failed to load giveaways from database: {e}")


# Helper: normalize chat id (string like -100123... or @channel or int)
def normalize_chat_id(chat_id):
    if isinstance(chat_id, int):
        return chat_id
    if isinstance(chat_id, str) and chat_id.lstrip('-').isdigit():
        return int(chat_id)
    return chat_id


# 1. FLASK SERVER TO KEEP RENDER ALIVE
app_flask = Flask('')


@app_flask.route('/')
def home():
    return "Zakmolanitech Bot is alive!"


def run_flask():
    app_flask.run(host='0.0.0.0', port=10000)


# 2. TELEGRAM BOT CODE
async def startgiveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new giveaway (admin-only).

    This handler shows the caller's Telegram ID in-chat, checks it against ADMIN_ID,
    and if authorized posts the giveaway message with an inline "Join" button.
    """
    global active_giveaway_id

    # Determine the invoking user id
    user = update.effective_user
    user_id = None
    if user:
        user_id = user.id
    elif update.effective_chat:
        user_id = update.effective_chat.id

    logging.info(f"startgiveaway invoked by user_id={user_id} ADMIN_ID={ADMIN_ID}")

    # First, show the caller their ID in-chat if possible (helps admins confirm their ID)
    id_displayed = False
    try:
        if update.message:
            await update.message.reply_text(f"🔍 Your Telegram ID is: `{user_id}`", parse_mode="Markdown")
            id_displayed = True
    except Exception as e:
        logging.warning(f"Could not display ID in-chat: {e}")

    # Try to DM the user their ID (original behavior). If we already displayed it in-chat, we
    # still attempt the DM but won't fallback to replying again.
    sent_dm = False
    if user_id is not None:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"Your Telegram ID is: `{user_id}`\n\nCopy this number.",
                parse_mode="Markdown"
            )
            sent_dm = True
        except Exception as e:
            logging.warning(f"Could not send DM to {user_id}: {e}")
            if not id_displayed and update.message:
                try:
                    await update.message.reply_text(
                        f"Your Telegram ID is: `{user_id}`\n\nCopy this number.",
                        parse_mode="Markdown"
                    )
                    sent_dm = True
                except Exception as e2:
                    logging.warning(f"Also could not reply in-chat: {e2}")

    if not sent_dm:
        logging.info("Could not deliver user ID message (user may not have started bot or chat context not available).")

    # Ensure we compare ints safely
    try:
        caller_id = int(user_id) if user_id is not None else None
    except Exception:
        caller_id = None

    # Helper to get a chat id to message back to the caller
    caller_chat = caller_id if caller_id is not None else (update.effective_chat.id if update.effective_chat else None)

    # Authorization check
    if caller_id is None or str(caller_id) != str(ADMIN_ID):
        try:
            if update.message:
                await update.message.reply_text("❌ You are not authorized to start a giveaway.")
            elif caller_chat is not None:
                await context.bot.send_message(chat_id=caller_chat, text="❌ You are not authorized to start a giveaway.")
        except Exception:
            logging.warning("Could not notify caller about unauthorized access.")
        return

    # Stop any active giveaway
    if active_giveaway_id is not None:
        logging.info(f"Stopping previous giveaway {active_giveaway_id}")
        if active_giveaway_id in giveaways:
            del giveaways[active_giveaway_id]

    # Build inline keyboard
    keyboard = [[InlineKeyboardButton("🎁 Join Giveaway", callback_data="join_giveaway")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Normalize CHANNEL_ID
    post_chat_id = normalize_chat_id(CHANNEL_ID)

    # Post giveaway
    try:
        msg = await context.bot.send_message(
            chat_id=post_chat_id,
            text="🔥 *NEW GIVEAWAY STARTED!* 🔥\n\nTap the button below to join!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        active_giveaway_id = msg.message_id
        giveaways[msg.message_id] = []
        save_giveaway_to_db(msg.message_id, str(CHANNEL_ID))

        # Confirm to admin
        try:
            if caller_chat is not None:
                await context.bot.send_message(chat_id=caller_chat, text=f"✅ Giveaway posted in {CHANNEL_ID}")
            elif update.message:
                await update.message.reply_text(f"✅ Giveaway posted in {CHANNEL_ID}")
        except Exception:
            logging.warning("Could not send confirmation message to admin.")

    except Exception as e:
        logging.exception(f"Failed to post giveaway to {CHANNEL_ID}: {e}")
        try:
            if caller_chat is not None:
                await context.bot.send_message(chat_id=caller_chat, text=f"❌ Failed to post giveaway to {CHANNEL_ID}: {e}")
        except Exception:
            logging.warning("Could not notify admin about posting failure.")
        return


async def stopgiveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the current giveaway and announce winner (admin-only)."""
    global active_giveaway_id

    user = update.effective_user
    user_id = user.id if user else None

    # Authorization check
    try:
        if int(user_id) != int(ADMIN_ID):
            await update.message.reply_text("❌ You are not authorized to stop a giveaway.")
            return
    except Exception:
        try:
            await update.message.reply_text("❌ You are not authorized to stop a giveaway.")
        except Exception:
            logging.warning("Could not send unauthorized message.")
        return

    if active_giveaway_id is None or active_giveaway_id not in giveaways:
        try:
            await update.message.reply_text("❌ No active giveaway to stop.")
        except Exception:
            logging.warning("Could not send no giveaway message.")
        return

    participants = giveaways.get(active_giveaway_id, [])

    if not participants:
        try:
            await update.message.reply_text("❌ No participants in the giveaway.")
        except Exception:
            logging.warning("Could not send no participants message.")
        return

    # Select random winner
    try:
        winner_id = random.choice(participants)
    except Exception as e:
        logging.error(f"Failed to pick a winner: {e}")
        try:
            await update.message.reply_text("❌ Failed to pick a winner.")
        except Exception:
            pass
        return

    # Normalize CHANNEL_ID
    post_chat_id = normalize_chat_id(CHANNEL_ID)

    # Announce winner
    try:
        await context.bot.send_message(
            chat_id=post_chat_id,
            text=f"🎉 *GIVEAWAY WINNER!* 🎉\n\nCongratulations to <a href='tg://user?id={winner_id}'>User {winner_id}</a>!\n\nTotal participants: {len(participants)}",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Failed to announce winner: {e}")

    # Clean up
    try:
        del giveaways[active_giveaway_id]
    except Exception:
        logging.warning("Could not delete giveaway from memory.")
    active_giveaway_id = None

    try:
        await update.message.reply_text(f"✅ Giveaway ended! Winner: {winner_id}")
    except Exception:
        logging.warning("Could not send confirmation message.")


async def pickwinner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pick a winner without stopping the giveaway (admin-only)."""
    user = update.effective_user
    user_id = user.id if user else None

    # Authorization check
    try:
        if int(user_id) != int(ADMIN_ID):
            await update.message.reply_text("❌ Not authorized")
            return
    except Exception:
        try:
            await update.message.reply_text("❌ Not authorized")
        except Exception:
            logging.warning("Could not send unauthorized message.")
        return

    if active_giveaway_id is None or active_giveaway_id not in giveaways:
        try:
            await update.message.reply_text("❌ No active giveaway to pick from.")
        except Exception:
            logging.warning("Could not send no giveaway message.")
        return

    participants = giveaways.get(active_giveaway_id, [])
    if not participants:
        try:
            await update.message.reply_text("❌ No participants in the giveaway.")
        except Exception:
            logging.warning("Could not send no participants message.")
        return

    try:
        winner_id = random.choice(participants)
    except Exception as e:
        logging.error(f"Failed to pick a winner: {e}")
        try:
            await update.message.reply_text("❌ Failed to pick a winner.")
        except Exception:
            pass
        return

    # Try to fetch winner info for nicer message
    winner_name = f"User {winner_id}"
    try:
        winner_chat = await context.bot.get_chat(winner_id)
        winner_name = winner_chat.first_name or winner_chat.username or winner_name
    except Exception:
        logging.info(f"Could not fetch chat for {winner_id}, announcing by ID.")

    post_chat_id = normalize_chat_id(CHANNEL_ID)
    try:
        await context.bot.send_message(
            chat_id=post_chat_id,
            text=f"🎉 WINNER: {winner_name}!\n\nCongratulations! DM me to claim your prize!"
        )
    except Exception as e:
        logging.error(f"Failed to announce winner via /pickwinner: {e}")

    try:
        await update.message.reply_text(f"Winner picked: {winner_name}")
    except Exception:
        logging.warning("Could not send confirmation message to admin.")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply with the caller's Telegram ID.

    Use this to confirm the numeric ID to put into ADMIN_ID.
    """
    user = update.effective_user
    user_id = None
    if user:
        user_id = user.id
    elif update.effective_chat:
        user_id = update.effective_chat.id

    if user_id is None:
        try:
            if update.message:
                await update.message.reply_text("Could not determine your Telegram ID.")
        except Exception:
            logging.warning("Could not send error message.")
        return

    text = f"Your Telegram ID is: `{user_id}`\n\nCopy this number and set it as ADMIN_ID in your environment."

    # First try to reply in the same chat
    try:
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logging.warning(f"Could not reply in-chat with ID: {e}")

    # Also try sending as a DM
    try:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
    except Exception as e:
        logging.info(f"Could not send DM with ID to {user_id}: {e}")


async def join_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Join Giveaway' button clicks."""
    query = update.callback_query

    # Safety check
    if not query or not query.message or not query.message.message_id:
        try:
            await query.answer("❌ Error: message context missing", show_alert=True)
        except Exception:
            logging.warning("Callback query missing context and cannot respond.")
        return

    # Acknowledge callback quickly
    try:
        await query.answer()
    except Exception:
        pass

    user = query.from_user
    msg_id = query.message.message_id

    if msg_id in giveaways:
        if user.id not in giveaways[msg_id]:
            giveaways[msg_id].append(user.id)
            add_participant_to_db(msg_id, user.id, user.username or "Unknown")
            try:
                await query.answer("✅ You have joined the giveaway!", show_alert=True)
            except Exception:
                pass
        else:
            try:
                await query.answer("⚠️ You already joined!", show_alert=True)
            except Exception:
                pass
    else:
        try:
            await query.answer("❌ Giveaway not found!", show_alert=True)
        except Exception:
            pass


def main():
    # Initialize database
    init_database()

    # Load giveaways from database on startup
    load_giveaways_from_db()

    # Start Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("startgiveaway", startgiveaway))
    app.add_handler(CommandHandler("stopgiveaway", stopgiveaway))
    app.add_handler(CommandHandler("pickwinner", pickwinner))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CallbackQueryHandler(join_giveaway, pattern="join_giveaway"))
    print("Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()
