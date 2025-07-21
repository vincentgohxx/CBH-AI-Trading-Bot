import os
import mimetypes
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update, InputFile

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Welcome to V-G Ai Trading Bot!")

def is_image(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith("image/")

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
