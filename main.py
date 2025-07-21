
import os
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Welcome to V-G Ai Trading Bot!")

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Error: BOT_TOKEN not found in environment variables.")
        return

    updater = Updater(token)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
