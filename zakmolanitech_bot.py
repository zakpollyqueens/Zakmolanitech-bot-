import os
import asyncio
import threading
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ['TOKEN']
CHANNEL_ID = os.environ['CHANNEL_ID']  # e.g. @ZakmolanitechSolutions or numeric id
ADMIN_ID = int(os.environ['ADMIN_ID']) # e.g. 123456789

# Store giveaway data in memory
giveaways = {}

# 1. FLASK SERVER TO KEEP RENDER ALIVE
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "Zakmolanitech Bot is alive!"


def run_flask():
    app_flask.run(host='0.0.0.0', port=10000)


# 2. TELEGRAM BOT CODE
async def startgiveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Determine the invoking user id (if available)
    user = update.effective_user
    user_id = None
    if user:
        user_id = user.id
    elif update.effective_chat:
        user_id = update.effective_chat.id

    logging.info(f"startgiveaway invoked by user_id={user_id} ADMIN_ID={ADMIN_ID}")

    # Try to DM the user their ID (works only if the user started the bot)
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
            # Fallback to replying in the same chat if possible
            if update.message:
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

    # Ensure we compare ints
    try:
        caller_id = int(user_id) if user_id is not None else None
    except Exception:
        caller_id = None

    # Helper to get a chat id to message back to the caller
    caller_chat = caller_id if caller_id is not None else (update.effective_chat.id if update.effective_chat else None)

    if caller_id != ADMIN_ID:
        # Notify the caller they are unauthorized
        try:
            if update.message:
                await update.message.reply_text("❌ You are not authorized to start a giveaway.")
            elif caller_chat is not None:
                await context.bot.send_message(chat_id=caller_chat, text="❌ You are not authorized to start a giveaway.")
        except Exception:
            logging.warning("Could not notify caller about unauthorized access.")
        return

    # Build inline keyboard
    keyboard = [[InlineKeyboardButton("🎁 Join Giveaway", callback_data="join_giveaway")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Normalize CHANNEL_ID: allow numeric ids or @username strings
    post_chat_id = CHANNEL_ID
    try:
        if isinstance(CHANNEL_ID, str) and CHANNEL_ID.lstrip('-').isdigit():
            post_chat_id = int(CHANNEL_ID)
    except Exception:
        post_chat_id = CHANNEL_ID

    # Post giveaway and handle failures
    try:
        msg = await context.bot.send_message(
            chat_id=post_chat_id,
            text="🔥 *NEW GIVEAWAY STARTED!* 🔥\n\nTap the button below to join!",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.exception(f"Failed to post giveaway to {CHANNEL_ID}: {e}")
        # Notify admin about the failure
        try:
            if caller_chat is not None:
                await context.bot.send_message(chat_id=caller_chat, text=f"Failed to post giveaway to {CHANNEL_ID}: {e}")
        except Exception:
            logging.warning("Could not notify admin about posting failure.")
        return

    # Track participants
    giveaways[msg.message_id] = []

    # Confirm to admin
    try:
        if caller_chat is not None:
            await context.bot.send_message(chat_id=caller_chat, text=f"✅ Giveaway posted in {CHANNEL_ID}")
        elif update.message:
            await update.message.reply_text(f"✅ Giveaway posted in {CHANNEL_ID}")
    except Exception:
        logging.warning("Could not send confirmation message to admin.")


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply with the caller's Telegram ID and attempt a DM as well.

    Use this to confirm the numeric ID to put into ADMIN_ID.
    """
    user = update.effective_user
    user_id = None
    if user:
        user_id = user.id
    elif update.effective_chat:
        user_id = update.effective_chat.id

    if user_id is None:
        # Nothing we can do
        if update.message:
            await update.message.reply_text("Could not determine your Telegram ID.")
        return

    text = f"Your Telegram ID is: `{user_id}`\n\nCopy this number and set it as ADMIN_ID in your environment." 

    # First try to reply in the same chat
    try:
        if update.message:
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logging.warning(f"Could not reply in-chat with ID: {e}")

    # Also try sending as a DM (works only if user started the bot)
    try:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
    except Exception as e:
        logging.info(f"Could not send DM with ID to {user_id}: {e}")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "join_giveaway":
        user = query.from_user
        msg_id = query.message.message_id # FIX: use .message.message_id

        if msg_id in giveaways:
            if user.id not in giveaways[msg_id]:
                giveaways[msg_id].append(user.id)
                await query.answer("✅ You have joined the giveaway!", show_alert=True)
            else:
                await query.answer("⚠️ You already joined!", show_alert=True)


def main():
    # Start Flask in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("startgiveaway", startgiveaway))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()
