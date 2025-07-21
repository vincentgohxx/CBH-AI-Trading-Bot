import os
import requests
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Welcome to CBH AI Trading Bot!")

def get_gold_price():
    url = "http://api.currencylayer.com/live"
    params = {
        "access_key": os.getenv("CURRENCY_API_KEY"),  # API Key 设置为环境变量
        "currencies": "XAU",
        "source": "USD",
        "format": 1
    }
    res = requests.get(url, params=params).json()
    if res.get("success"):
        price_per_usd = res["quotes"]["USDXAU"]
        gold_price = round(1 / price_per_usd, 2)
        return f"当前黄金 XAU/USD 价格为：${gold_price} 美元/盎司"
    else:
        return "❌ 查询黄金价格失败，请稍后再试。"

def gold_handler(update: Update, context: CallbackContext):
    text = get_gold_price()
    update.message.reply_text(text)

def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Error: BOT_TOKEN not found in environment variables.")
        return

    updater = Updater(token)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("gold", gold_handler))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
