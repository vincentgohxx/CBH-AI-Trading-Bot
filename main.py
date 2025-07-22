import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, 
                          CallbackContext, PicklePersistence, CallbackQueryHandler)
import requests
from openai import OpenAI
import base64
from PIL import Image
from functools import wraps
from datetime import datetime, date

# 从 prompts.py 文件中导入AI指令
from prompts import PROMPT_ANALYST_V2

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
    "start_welcome": { "cn": "欢迎使用 CBH AI 交易助手 (MVP v1.1 - 交互版)！", "en": "Welcome to CBH AI Trading Assistant (MVP v1.1 - Interactive)!" },
    "start_features": {
        "cn": ("**核心功能:**\n"
               "1️⃣ **/analyze**: 上传图表，获取专业AI分析。\n"
               "2️⃣ **/price**: 获取热门交易对的实时行情。\n"
               "3️⃣ **/language**: 切换语言偏好。\n"
               "4️⃣ **/help**: 查看所有指令。"),
        "en": ("**Core Features:**\n"
               "1️⃣ **/analyze**: Upload a chart for professional AI analysis.\n"
               "2️⃣ **/price**: Get real-time quotes for popular pairs.\n"
               "3️⃣ **/language**: Switch your language preference.\n"
               "4️⃣ **/help**: Show all commands.")
    },
}

def get_text(key, lang_code):
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
    update.message.reply_text("Available Commands:\n/start\n/help\n/price\n/analyze\n/language")

def language(update: Update, context: CallbackContext) -> None:
    from telegram import ReplyKeyboardMarkup # 临时导入
    keyboard = [["English Only"], ["中文"], ["English + 中文 (Both)"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Please select your preferred language:", reply_markup=reply_markup)

def set_language(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    if "English Only" in text: context.user_data['lang'] = 'en'; update.message.reply_text("Language set to English.")
    elif "中文" in text: context.user_data['lang'] = 'cn'; update.message.reply_text("语言已设置为中文。")
    else: context.user_data['lang'] = 'both'; update.message.reply_text("Language set to English + 中文.")

def get_price(symbol: str) -> dict:
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY 未设置！行情功能无法运行。")
        return {"error": "行情服务未配置。"}
    url = f"https://financialmodelingprep.com/api/v3/quote/{symbol.upper()}?apikey={FMP_API_KEY}"
    logger.info(f"正在从URL请求价格: {url}")
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            quote = data[0]
            return { "name": quote.get("name", symbol), "price": quote.get("price"), "change": quote.get("change", 0), "changesPercentage": quote.get("changesPercentage", 0) }
        else:
            return {"error": f"找不到交易对 {symbol} 的数据。"}
    except requests.RequestException as e:
        logger.error(f"获取 {symbol} 价格时出错: {e}")
        return {"error": "获取行情失败，请稍后再试。"}

# 【新】这个函数现在只负责弹出按钮
def price_command(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("🥇 黄金 (XAUUSD)", callback_data='price_XAUUSD'), InlineKeyboardButton("🇪🇺 欧元/美元 (EURUSD)", callback_data='price_EURUSD')],
        [InlineKeyboardButton("🇬🇧 英镑/美元 (GBPUSD)", callback_data='price_GBPUSD'), InlineKeyboardButton("🇯🇵 美元/日元 (USDJPY)", callback_data='price_USDJPY')],
        [InlineKeyboardButton("₿ 比特币 (BTCUSD)", callback_data='price_BTCUSD'), InlineKeyboardButton("Ξ 以太坊 (ETHUSD)", callback_data='price_ETHUSD')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('请选择您想查询的交易对:', reply_markup=reply_markup)

# 【新】这个全新的函数负责处理所有按钮的点击
def button_callback_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    command, symbol = query.data.split('_', 1)

    if command == 'price':
        query.edit_message_text(text=f"正在查询 {symbol} 的实时行情...")
        data = get_price(symbol)
        if "error" in data:
            response_text = f"❌ {data['error']}"
        else:
            change_sign = "📈" if data.get('change', 0) > 0 else "📉"
            response_text = (
                f"**行情速览: {data.get('name', symbol)} ({symbol})**\n\n"
                f"🔹 **当前价格:** `{data.get('price', 'N/A')}`\n"
                f"{change_sign} **价格变动:** `{data.get('change', 'N/A')} ({data.get('changesPercentage', 0):.2f}%)`\n"
            )
        query.edit_message_text(text=response_text, parse_mode='Markdown')

def analyze_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("Please upload a chart image (JPG/PNG) now for analysis.")

def analyze_chart(image_path: str, lang_code: str) -> str:
    if not client: return "抱歉，AI服务因配置问题未能启动。"
    
    # 根据用户的语言偏好，选择正确的Prompt
    prompt_text = PROMPT_ANALYST_V2.get(lang_code, PROMPT_ANALYST_V2['en']) # 默认用英文

    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        logger.info(f"正在使用模型 {AI_MODEL_NAME} 分析图表...")
        response = client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
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
    
    # 获取用户的语言设置
    lang = context.user_data.get('lang', 'both')
    # 如果是双语，我们优先用中文Prompt，因为它的格式要求更符合您的期望
    prompt_lang = 'cn' if lang in ['cn', 'both'] else 'en'

    # 将语言偏好传递给分析函数
    analysis_result = analyze_chart(temp_photo_path, prompt_lang)
    
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
    dispatcher.add_handler(CommandHandler("price", price_command)) # /price 现在弹出按钮
    dispatcher.add_handler(CommandHandler("analyze", analyze_command))
    dispatcher.add_handler(CommandHandler("language", language))
    
    # 【新】注册我们全新的按钮回调处理器
    dispatcher.add_handler(CallbackQueryHandler(button_callback_handler))
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.regex('^(English Only|中文|English \+ 中文 \(Both\))$'), set_language))

    updater.start_polling()
    logger.info("CBH AI 交易助手 (MVP v1.1 - 交互版) 已成功启动！")
    updater.idle()

if __name__ == '__main__':
    main()
