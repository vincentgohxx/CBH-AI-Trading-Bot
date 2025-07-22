# supabase/functions/telegram-bot/index.py

import os
import json
import asyncio
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --- 临时的模拟函数 ---
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("欢迎使用 Supabase (Docker版) CBH AI 交易助手！")

def handle_text(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(f"我收到了你的消息: {update.message.text}")

# --- Webhook 主处理逻辑 ---
bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    raise ValueError("环境变量 BOT_TOKEN 未设置！")

bot = Bot(token=bot_token)
dispatcher = Dispatcher(bot, None, use_context=True)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

async def handler(scope, receive, send):
    """ASGI 入口函数，用于处理 Supabase 的请求。"""
    assert scope['type'] == 'http'
    
    # 从请求中读取body
    body_bytes = b''
    more_body = True
    while more_body:
        message = await receive()
        body_bytes += message.get('body', b'')
        more_body = message.get('more_body', False)

    try:
        update_data = json.loads(body_bytes)
        update = Update.de_json(update_data, bot)
        
        # 使用 asyncio.create_task 在后台处理更新，并立即返回响应
        # 这样可以避免Telegram的超时问题
        asyncio.create_task(dispatcher.process_update(update))
        
        # 立即向 Supabase 返回一个成功的响应
        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': b'OK',
        })
        
    except Exception as e:
        print(f"处理更新时出错: {e}")
        await send({
            'type': 'http.response.start',
            'status': 500,
            'headers': [[b'content-type', b'text/plain']],
        })
        await send({
            'type': 'http.response.body',
            'body': str(e).encode(),
        })

# 为 gunicorn 提供一个可调用的 app
handler_asgi = handler
