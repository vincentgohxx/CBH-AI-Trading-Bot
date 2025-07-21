import logging
import os
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

def start(update: Update, context: CallbackContext):
    update.message.reply_text("欢迎使用 V-G Ai Trading Bot! 输入 /price 获取黄金价格")

def price(update: Update, context: CallbackContext):
    update.message.reply_text("当前黄金价功能开发中…🛠️（后续支持图表上传解析）")

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("price", price))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
