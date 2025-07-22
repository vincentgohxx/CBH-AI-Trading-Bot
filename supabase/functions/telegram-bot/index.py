# supabase/functions/telegram-bot/index.py

import os
import json
from telegram import Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# 模拟我们未来的数据库和AI模块
# 注意：这只是一个临时的框架，我们稍后会用真正的数据库和AI逻辑来替换它

def get_price(symbol: str) -> dict:
    # 这是一个临时的模拟函数
    return {"price": 2350.50, "change": 10.25, "changesPercentage": 0.44}

# --- Telegram 机器人处理器 ---

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("欢迎使用 Supabase 版 CBH AI 交易助手！")

def gold_command(update: Update, context: CallbackContext) -> None:
    data = get_price("XAUUSD")
    update.message.reply_text(f"黄金当前价格: ${data['price']}")
    
def handle_text(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(f"我收到了你的消息: {update.message.text}")

# --- Webhook 主处理函数 ---

def handler(request):
    """Supabase Edge Function 的主入口函数。"""
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("错误: 环境变量 BOT_TOKEN 未设置！")
        return {"status": 500, "body": "Bot token not configured."}

    # 初始化一个临时的Bot和Dispatcher
    from telegram import Bot
    bot = Bot(token=bot_token)
    dispatcher = Dispatcher(bot, None, use_context=True)

    # 注册我们需要的指令处理器
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("gold", gold_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    try:
        # 从请求体中解析Telegram发送过来的更新
        update_data = json.loads(request.get_data().decode('utf-8'))
        update = Update.de_json(update_data, bot)
        
        # 让Dispatcher处理这个更新
        dispatcher.process_update(update)
        
        # 返回一个成功的响应
        return {"status": 200, "body": "OK"}

    except Exception as e:
        print(f"处理更新时出错: {e}")
        return {"status": 400, "body": str(e)}
