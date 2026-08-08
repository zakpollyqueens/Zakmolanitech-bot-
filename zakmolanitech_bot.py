import os
import asyncio
import threading
import logging
import sqlite3
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
ADMIN_ID = int(os.environ['ADMIN_ID'])

# Store giveaway data in memory (with database backup for persistence)
giveaways = {}
active_giveaway_id = None  # Track the current giveaway message ID

# Database setup for persistence
DB_PATH = 'giveaways.db'

def init_database():
    """Initialize SQLite database for giveaway persistence."""
    conn = sqlite3.connect(DB_PATH)
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO giveaways (message_id, channel_id, created_at, participants)
            VALUES (?, ?, ?, ?)
        ''', (msg_id, channel_id, datetime.now(), ''))
        conn.commit()
        conn.close()
        logging.info(f"Giveaway {msg_id} saved to database")
    except Exception as e:
        logging.error(f"Failed to save giveaway to database: {e}")

def add_participant_to_db(msg_id, user_id, username):
    """Add participant to database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO participants (giveaway_id, user_id, username, joined_at)
            VALUES (?, ?, ?, ?)
        ''', (msg_id, user_id, username, datetime.now()))
        conn.commit()
        conn.close()
        logging.info(f"Participant {user_id} added to giveaway {msg_id}")
    except Exception as e:
        logging.error(f"Failed to add participant to database: {e}")

# 1. FLASK SERVER TO KEEP RENDER ALIVE
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Zakmolanitech Bot is alive!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=10000)

# 2. TELEGRAM BOT CODE
async def startgiveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # THIS LINE WILL SHOW YOUR ID
    await update.message.reply_text(f"🔍 Your Telegram ID is: `{user_id}`", parse_mode="Markdown")
    
    if str(ADMIN_ID) != str(user_id):
        await update.message.reply_text("❌ You are not authorized to start a giveaway.")
        return
    
    # put the rest of your giveaway code here
    await update.message.reply_text("✅ You are authorized! Starting giveaway...")

async def stopgiveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the current giveaway and announce winner (admin-only)."""
    global active_giveaway_id
    
    user = update.effective_user
    user_id = user.id if user else None

    # Authorization check
    if user_id != ADMIN_ID:
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

    participants = giveaways[active_giveaway_id]
    
    if not participants:
        try:
            await update.message.reply_text("❌ No participants in the giveaway.")
        except Exception:
            logging.warning("Could not send no participants message.")
        return

    # Select random winner
    import random
    winner_id = random.choice(participants)
    
    # Normalize CHANNEL_ID
    post_chat_id = CHANNEL_ID
    try:
        if isinstance(CHANNEL_ID, str) and CHANNEL_ID.lstrip('-').isdigit():
            post_chat_id = int(CHANNEL_ID)
    except Exception:
        post_chat_id = CHANNEL_ID

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
    del giveaways[active_giveaway_id]
    active_giveaway_id = None
    
    try:
        await update.message.reply_text(f"✅ Giveaway ended! Winner: {winner_id}")
    except Exception:
        logging.warning("Could not send confirmation message.")

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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks for giveaway participation."""
    query = update.callback_query
    
    # Safety check
    if not query.message or not query.message.message_id:
        await query.answer("❌ Error: message context missing", show_alert=True)
        return

    await query.answer()

    if query.data == "join_giveaway":
        user = query.from_user
        msg_id = query.message.message_id

        if msg_id in giveaways:
            if user.id not in giveaways[msg_id]:
                giveaways[msg_id].append(user.id)
                add_participant_to_db(msg_id, user.id, user.username or "Unknown")
                await query.answer("✅ You have joined the giveaway!", show_alert=True)
            else:
                await query.answer("⚠️ You already joined!", show_alert=True)
        else:
            await query.answer("❌ Giveaway not found!", show_alert=True)

def main():
    # Initialize database
    init_database()
    
    # Start Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("startgiveaway", startgiveaway))
    app.add_handler(CommandHandler("stopgiveaway", stopgiveaway))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
