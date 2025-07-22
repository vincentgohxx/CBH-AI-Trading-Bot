# supabase/functions/telegram-bot/index.py
import os
import json
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
from fastapi import FastAPI, Request

# 初始化 FastAPI app，这是 Gunicorn 需要的
app = FastAPI()

bot_token = os.getenv("8189696717:AAEHt1aEPosYYsBaxPxAfaKaNwtA19hu2xs")
if not bot_token:
    raise ValueError("环境变量 BOT_TOKEN 未设置！")

bot = Bot(token=bot_token)
dispatcher = Dispatcher(bot, None, use_context=True)

# --- 我们的机器人指令 ---
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("欢迎使用 Supabase (Docker最终版) CBH AI 交易助手！")

dispatcher.add_handler(CommandHandler("start", start))

@app.post("/")
async def handler(request: Request):
    """FastAPI 入口，处理来自Telegram的Webhook请求。"""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, bot)
        dispatcher.process_update(update)
        return {"status": "OK"}
    except Exception as e:
        print(f"处理更新时出错: {e}")
        return {"status": "Error"}
