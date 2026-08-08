import os
import asyncio
import threading
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

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
CHANNEL_ID = os.environ['CHANNEL_ID']  # e.g. @ZakmolanitechSolutions
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
    user_id = update.effective_user.id
    print(f"DEBUG: User who ran command = {user_id}")  
    
    if str(ADMIN_ID) != str(user_id):
        await update.message.reply_text("❌ You are not authorized to start a giveaway.")
        return
    keyboard = [
        [InlineKeyboardButton("🎁 Join Giveaway", callback_data="join_giveaway")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text="🔥 *NEW GIVEAWAY STARTED!* 🔥\n\nTap the button below to join!",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    giveaways[msg.message_id] = []
    await update.message.reply_text(f"✅ Giveaway posted in {CHANNEL_ID}")


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
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()
