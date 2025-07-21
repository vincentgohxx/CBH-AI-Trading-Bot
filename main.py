import logging
import os
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update

# 加载.env中的Bot Token
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# 设置日志
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# /start 命令处理
def start(update: Update, context: CallbackContext):
    update.message.reply_text("欢迎使用 CBH_Ai_TradingBot! ✅\n请输入指令，例如 /price 获取黄金价。")

# /price 命令处理（目前示例，后面可以对接API）
def price(update: Update, context: CallbackContext):
    update.message.reply_text("当前黄金价格功能正在开发中 ✨（你可以上传图表进行分析）")

# 主函数
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # 添加命令处理器
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("price", price))

    # 启动 bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()