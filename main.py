import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, 
                          CallbackContext, PicklePersistence)
import requests
from openai import OpenAI
import base64
from PIL import Image
from functools import wraps
from datetime import datetime, date

# 从我们新建的 prompts.py 文件中导入AI指令
from prompts import PROMPT_ANALYST_V1

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 核心配置 ---
AI_MODEL_NAME = 'gpt-4o'
client = None
try:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = OpenAI(api_key=api_key)
    else:
        logger.critical("环境变量 OPENAI_API_KEY 未设置！")
except Exception as e:
    logger.critical(f"OpenAI 客户端初始化失败: {e}")

FMP_API_KEY = os.getenv("FMP_API_KEY")

# --- 多语言文本管理 ---
LANGUAGES = {
    "start_welcome": { "cn": "欢迎使用 CBH AI 交易助手 (MVP v1.0)！", "en": "Welcome to CBH AI Trading Assistant (MVP v1.0)!" },
    "start_features": {
        "cn": ("**核心功能:**\n"
               "1️⃣ **/analyze**: 上传图表，获取专业AI分析。\n"
               "2️⃣ **/gold**: 查询黄金(XAUUSD)实时行情。\n"
               "3️⃣ **/language**: 切换语言偏好。\n"
               "4️⃣ **/help**: 查看所有指令。"),
        "en": ("**Core Features:**\n"
               "1️⃣ **/analyze**: Upload a chart for professional AI analysis.\n"
               "2️⃣ **/gold**: Get real-time quotes for Gold (XAUUSD).\n"
               "3️⃣ **/language**: Switch your language preference.\n"
               "4️⃣ **/help**: Show all commands.")
    },
    # ... 您可以在这里添加所有机器人需要用到的文本 ...
}

def get_text(key, lang_code):
    """根据用户的语言偏好获取文本。"""
    if lang_code == 'cn': return LANGUAGES[key].get('cn')
    elif lang_code == 'en': return LANGUAGES[key].get('en')
    else: return f"{LANGUAGES[key].get('en')}\n\n{LANGUAGES[key].get('cn')}"

# --- 核心功能处理器 ---

def start(update: Update, context: CallbackContext) -> None:
    context.user_data.setdefault('lang', 'both')
    lang = context.user_data['lang']
    welcome_text = get_text('start_welcome', lang)
    features_text = get_text('start_features', lang)
    update.message.reply_text(f"{welcome_text}\n\n{features_text}", parse_mode='Markdown')

def help_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Available Commands:\n/start\n/help\n/gold\n/analyze\n/language")

def language(update: Update, context: CallbackContext) -> None:
    keyboard = [["English Only"], ["中文"], ["English + 中文 (Both)"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Please select your preferred language:", reply_markup=reply_markup)

def set_language(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    if "English Only" in text: context.user_data['lang'] = 'en'; update.message.reply_text("Language set to English.")
    elif "中文" in text: context.user_data['lang'] = 'cn'; update.message.reply_text("语言已设置为中文。")
    else: context.user_data['lang'] = 'both'; update.message.reply_text("Language set to English + 中文.")

def get_price(symbol: str = "XAUUSD") -> dict:
    if not FMP_API_KEY: return {"error": "行情服务未配置。"}
    formatted_symbol = symbol.upper()
    if len(symbol) == 6 and symbol not in ["GOLD", "SILVER"]:
        formatted_symbol = f"{symbol[:3]}/{symbol[3:]}"
    url = f"https://financialmodelingprep.com/api/v3/quote/{formatted_symbol}?apikey={FMP_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            return { "name": data[0].get("name", symbol), "price": data[0].get("price"), "change": data[0].get("change", 0), "changesPercentage": data[0].get("changesPercentage", 0) }
        return {"error": f"找不到交易对 {symbol} 的数据。"}
    except requests.RequestException as e:
        logger.error(f"获取 {symbol} 价格时出错: {e}")
        return {"error": "获取行情失败，请稍后再试。"}

def gold_command(update: Update, context: CallbackContext) -> None:
    symbol = "XAUUSD"
    data = get_price(symbol)
    if "error" in data:
        update.message.reply_text(f"❌ {data['error']}")
        return
    change_sign = "📈" if data.get('change', 0) > 0 else "📉"
    response_text = (
        f"**行情速览: {data.get('name', symbol)} ({symbol})**\n\n"
        f"🔹 **当前价格:** `{data.get('price', 'N/A')}`\n"
        f"{change_sign} **价格变动:** `{data.get('change', 'N/A')} ({data.get('changesPercentage', 0):.2f}%)`\n"
    )
    update.message.reply_text(response_text, parse_mode='Markdown')

def analyze_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Please upload a chart image (JPG/PNG) now for analysis.")

def analyze_chart(image_path: str) -> str:
    if not client: return "抱歉，AI服务因配置问题未能启动。"
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        logger.info(f"正在使用模型 {AI_MODEL_NAME} 分析图表...")
        response = client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[{"role": "user","content": [{"type": "text","text": PROMPT_ANALYST_V1['cn']},{"type": "image_url","image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
            max_tokens=500
        )
        analysis_result = response.choices[0].message.content
        return analysis_result.replace("```", "").strip()
    except Exception as e:
        logger.error(f"调用OpenAI API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("收到图表，正在为您生成一份专业的交易信号，请稍候...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    analysis_result = analyze_chart(temp_photo_path)
    try:
        reply.edit_text(analysis_result, parse_mode='Markdown')
    except Exception:
        reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return
        
    persistence = PicklePersistence(filename='bot_data')
    updater = Updater(bot_token, use_context=True, persistence=persistence)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("gold", gold_command))
    dispatcher.add_handler(CommandHandler("analyze", analyze_command))
    dispatcher.add_handler(CommandHandler("language", language))
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.regex('^(English Only|中文|English \+ 中文 \(Both\))$'), set_language))

    updater.start_polling()
    logger.info("CBH AI 交易助手 (MVP v1.0) 已成功启动！")
    updater.idle()

if __name__ == '__main__':
    main()
