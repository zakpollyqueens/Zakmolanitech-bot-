import os, asyncio, random
from telegram.ext import Application, CommandHandler

TOKEN = os.environ['TOKEN']
CHANNEL_ID = "@ZakmolanitechSolutions"

tech_tips = [
    "💡 Clear WhatsApp cache: Settings > Storage",
    "📱 Dial *100# for MTN/Airtel bundles",
    "💻 Learn Python, get remote jobs"
]
participants = []

async def tech_poster(app):
    while True:
        await asyncio.sleep(14400) # 4 hours
        tip = random.choice(tech_tips)
        await app.bot.send_message(chat_id=CHANNEL_ID, text=f"*ZAKMOLANITECH SOLUTIONS*\n\n{tip}\n\n#TechTips", parse_mode="Markdown")

async def start_giveaway(update, context):
    global participants
    participants = []
    await context.bot.send_message(chat_id=CHANNEL_ID, text="🎁 *GIVEAWAY STARTED*\nReply 'JOIN' to enter.", parse_mode="Markdown")

async def join_giveaway(update, context):
    global participants
    user = update.message.from_user.username
    if user and user not in participants:
        participants.append(user)
        await update.message.reply_text("✅ You entered the giveaway!")

async def end_giveaway(update, context):
    global participants
    if participants:
        winner = random.choice(participants)
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"🎉 WINNER: @{winner}\nDM us to claim!", parse_mode="Markdown")
        participants = []
    else:
        await context.bot.send_message(chat_id=CHANNEL_ID, text="No one joined 😢")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("startgiveaway", start_giveaway))
    app.add_handler(CommandHandler("join", join_giveaway))
    app.add_handler(CommandHandler("endgiveaway", end_giveaway))
    asyncio.get_event_loop().create_task(tech_poster(app))
    app.run_polling()

if __name__ == "__main__": 
    main()
