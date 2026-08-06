import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# READ SECRETS FROM RENDER
TOKEN = os.environ['TOKEN_ID']
CHANNEL_ID = os.environ['CHANNEL_ID']
ADMIN_ID = int(os.environ['ADMIN_ID'])

async def start_giveaway(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await context.bot.send_message(
        chat_id=CHANNEL_ID,
        text="🎉 GIVEAWAY STARTED! 🎉\n\nReact to join!"
    )

def main():
    print("Bot is running...")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("startgiveaway", start_giveaway))
    app.run_polling()

if __name__ == '__main__':
    main()
