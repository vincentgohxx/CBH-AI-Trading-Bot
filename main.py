import os
import logging
from telegram import Update
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, 
                          CallbackContext, PicklePersistence) # 导入PicklePersistence

import requests
import google.generativeai as genai
from PIL import Image
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 【新增】管理员与统计系统 ---
# 从环境变量中读取管理员ID
try:
    ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))
    if ADMIN_USER_ID == 0:
        logger.warning("警告: 未设置管理员ID (ADMIN_USER_ID)，统计功能将无法安全使用！")
except ValueError:
    logger.error("错误: ADMIN_USER_ID 格式不正确，必须为纯数字！")
    ADMIN_USER_ID = 0

def restricted_to_admin(func):
    """一个装饰器，用于限制只有管理员才能访问。"""
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_USER_ID:
            logger.warning(f"非管理员用户 {user_id} 尝试访问管理员指令。")
            return
        return func(update, context, *args, **kwargs)
    return wrapped

def track_usage(func):
    """一个装饰器，用于追踪用户ID和使用次数。"""
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        
        # 使用bot_data存储全局信息
        if 'user_ids' not in context.bot_data:
            context.bot_data['user_ids'] = set()
        context.bot_data['user_ids'].add(user_id)
        
        if 'total_usage' not in context.bot_data:
            context.bot_data['total_usage'] = 0
        context.bot_data['total_usage'] += 1
        
        return func(update, context, *args, **kwargs)
    return wrapped

# --- 机器人专家人设 (代码不变) ---
ULTIMATE_ANALYST_PROMPT_ZH = (
    "你是一位顶级的技术分析师..." # 内容与上一版相同
)

# --- 核心配置 ---
AI_MODEL_NAME = 'gemini-1.5-flash'
# ... 其他配置 ...

# --- 【新增】管理员指令 ---
@restricted_to_admin
def stats(update: Update, context: CallbackContext) -> None:
    """显示机器人使用统计数据。"""
    total_users = len(context.bot_data.get('user_ids', set()))
    total_usage = context.bot_data.get('total_usage', 0)
    
    response_text = (
        f"📊 **机器人运营后台**\n\n"
        f"👤 **总用户数:** {total_users} 位\n"
        f"🚀 **总使用次数:** {total_usage} 次\n\n"
        f"数据最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    update.message.reply_text(response_text, parse_mode='Markdown')

# --- 价格监控功能 (代码不变) ---
def get_gold_price():
    # ...
def check_prices(context: CallbackContext):
    # ...

# --- 所有核心功能都需要加上新的追踪装饰器 ---
@track_usage
def watch(update: Update, context: CallbackContext) -> None:
    # ... (函数内部代码与上一版完全相同) ...

@track_usage
def handle_photo(update: Update, context: CallbackContext) -> None:
    # ... (函数内部代码与上一版完全相同) ...

# ... 其他函数(start, AI分析等) ...

# 为了让代码块完整，我把所有被省略的函数也粘贴进来
FMP_API_KEY = os.getenv("FMP_API_KEY")
model = None
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(AI_MODEL_NAME)
except Exception as e:
    logger.critical(f"Google AI 初始化失败: {e}")

def get_gold_price():
    if not FMP_API_KEY: return None
    url = f"https://financialmodelingprep.com/api/v3/quote/XAUUSD?apikey={FMP_API_KEY}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data and 'price' in data[0]: return data[0]['price']
    except requests.RequestException as e:
        logger.error(f"获取黄金价格时出错: {e}")
    return None

def check_prices(context: CallbackContext):
    job = context.job
    chat_id, target_price, condition = job.context['chat_id'], job.context['target_price'], job.context['condition']
    current_price = get_gold_price()
    if current_price is None: return
    alert = (condition == '>' and current_price > target_price) or \
            (condition == '<' and current_price < target_price)
    if alert:
        text = f"**🚨 价格警报: 黄金 (XAUUSD) 🚨**\n\n您设置的条件 **(价格 {condition} {target_price})** 已满足！\n\n**当前价格: ${current_price:,.2f}**"
        context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        job.schedule_removal()

def analyze_chart_as_analyst(image_path: str) -> str:
    if not model: return "抱歉，AI服务未启动。"
    try:
        img = Image.open(image_path)
        prompt = f"{ULTIMATE_ANALYST_PROMPT_ZH}\n\n请严格按照以上格式，分析这张图表。"
        response = model.generate_content([prompt, img])
        return response.text.replace("```", "").strip()
    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("欢迎使用 CBH AI 精英分析师 & 哨兵 (v8.0 - 运营版)！...")

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return

    # 【重要】初始化持久化存储
    persistence = PicklePersistence(filename='bot_data')
    
    # 【重要】将 persistence 对象传递给 Updater
    updater = Updater(bot_token, use_context=True, persistence=persistence)
    
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("watch", watch))
    dispatcher.add_handler(CommandHandler("stats", stats)) # 新增的管理员指令
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))

    updater.start_polling()
    logger.info("CBH AI 精英分析师 & 哨兵机器人已成功启动！(运营版)")
    updater.idle()

if __name__ == '__main__':
    main()
