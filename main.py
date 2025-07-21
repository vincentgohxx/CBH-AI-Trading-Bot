import os
import logging
from telegram import Update
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters, 
                          CallbackContext, PicklePersistence)
import requests
import google.generativeai as genai
from PIL import Image
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from datetime import datetime

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 管理员与统计系统 ---
try:
    ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID', 0))
    if ADMIN_USER_ID == 0:
        logger.warning("警告: 未设置管理员ID (ADMIN_USER_ID)，统计功能将无法安全使用！")
except (ValueError, TypeError):
    logger.error("错误: ADMIN_USER_ID 格式不正确，必须为纯数字！")
    ADMIN_USER_ID = 0

def restricted_to_admin(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_USER_ID:
            logger.warning(f"非管理员用户 {user_id} 尝试访问管理员指令。")
            return
        return func(update, context, *args, **kwargs)
    return wrapped

def track_usage(func):
    @wraps(func)
    def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if 'user_ids' not in context.bot_data:
            context.bot_data['user_ids'] = set()
        context.bot_data['user_ids'].add(user_id)
        
        if 'total_usage' not in context.bot_data:
            context.bot_data['total_usage'] = 0
        context.bot_data['total_usage'] += 1
        
        return func(update, context, *args, **kwargs)
    return wrapped

# --- 机器人专家人设 ---
ULTIMATE_ANALYST_PROMPT_ZH = (
    "你是一位顶级的技术分析师..." # (为了简洁，这里省略，但代码中是完整的)
)

# --- 核心配置 ---
AI_MODEL_NAME = 'gemini-1.5-flash'
model = None
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(AI_MODEL_NAME)
    else:
        logger.critical("环境变量 GOOGLE_API_KEY 未设置！")
except Exception as e:
    logger.critical(f"Google AI 初始化失败: {e}")

FMP_API_KEY = os.getenv("FMP_API_KEY")

# --- 管理员指令 ---
@restricted_to_admin
def stats(update: Update, context: CallbackContext) -> None:
    total_users = len(context.bot_data.get('user_ids', set()))
    total_usage = context.bot_data.get('total_usage', 0)
    
    response_text = (
        f"📊 **机器人运营后台**\n\n"
        f"👤 **总用户数:** {total_users} 位\n"
        f"🚀 **总使用次数:** {total_usage} 次\n\n"
        f"数据最后更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    update.message.reply_text(response_text, parse_mode='Markdown')

# --- 价格监控功能 (已恢复完整代码) ---
def get_gold_price():
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY 未设置！价格监控功能无法运行。")
        return None
    url = f"https://financialmodelingprep.com/api/v3/quote/XAUUSD?apikey={FMP_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data and 'price' in data[0]:
            return data[0]['price']
    except requests.RequestException as e:
        logger.error(f"获取黄金价格时出错: {e}")
    return None

def check_prices(context: CallbackContext):
    job = context.job
    chat_id = job.context['chat_id']
    target_price = job.context['target_price']
    condition = job.context['condition']
    current_price = get_gold_price()
    if current_price is None: return
    logger.info(f"检查价格: 当前={current_price}, 目标={target_price}, 条件={condition}")
    alert = False
    if condition == '>' and current_price > target_price: alert = True
    elif condition == '<' and current_price < target_price: alert = True
    if alert:
        text = (f"**🚨 价格警报: 黄金 (XAUUSD) 🚨**\n\n"
                f"您设置的条件 **(价格 {condition} {target_price})** 已满足！\n\n"
                f"**当前价格: ${current_price:,.2f}**")
        context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        job.schedule_removal()

# --- 核心功能 (已恢复完整代码) ---
@track_usage
def watch(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    try:
        condition = context.args[0]
        target_price = float(context.args[1])
        if condition not in ['>', '<']: raise ValueError()
        job_context = {'chat_id': chat_id, 'target_price': target_price, 'condition': condition}
        context.job_queue.run_repeating(check_prices, interval=300, first=0, context=job_context, name=f"watch_{chat_id}_{condition}_{target_price}")
        update.message.reply_text(f"✅ **监控已设置**\n当黄金价格 **{condition} ${target_price:,.2f}** 时，我会提醒您。", parse_mode='Markdown')
    except (IndexError, ValueError):
        update.message.reply_text("❌ **指令格式错误！**\n请这样使用:\n`/watch > 2380`\n`/watch < 2300`")

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

@track_usage
def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("收到图表，正在为您生成一份专业的交易信号，请稍候...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    analysis_result = analyze_chart_as_analyst(temp_photo_path)
    try:
        reply.edit_text(analysis_result, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"Markdown发送失败: {e}。将尝试用纯文本发送。")
        reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text("欢迎使用 CBH AI 精英分析师 & 哨兵 (v8.0 - 运营版)！...")

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return

    persistence = PicklePersistence(filename='bot_data')
    updater = Updater(bot_token, use_context=True, persistence=persistence)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("watch", watch))
    dispatcher.add_handler(CommandHandler("stats", stats))
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))

    updater.start_polling()
    logger.info("CBH AI 精英分析师 & 哨兵机器人已成功启动！(运营版)")
    updater.idle()

# 为了让代码块完整，把省略的PROMPT也加上
ULTIMATE_ANALYST_PROMPT_ZH = (
    "你是一位顶级的技术分析师，名为'CBH AI交易专家'，专长是提供简洁、结构化、可执行的交易信号。\n\n"
    "你的任务流程分为两步：\n"
    "1. **第一步（强制执行）：** 你必须首先从图片中**识别出交易符号和时间周期**（例如：GOLD, H4, D1）。\n"
    "2. **第二步：** 基于你识别出的信息和图表形态，你的回答**必须严格、完全地遵循**以下格式，不得有任何偏差：\n\n"
    "```\n"
    "📊 **分析结果（[这里填入识别出的交易符号和周期]）**\n\n"
    "📈 **趋势：** [此处填写你对趋势的简洁分析，并说明关键技术原因]\n\n"
    "📌 **支撑位：** [价格1] / [价格2]\n"
    "📌 **阻力位：** [价格1] / [价格2]\n\n"
    "🎯 **推荐操作：**\n"
    "[做多/做空]（[此处填写具体的入场条件]） → **止损设** [止损价格] → **目标价：** [目标价1] / [目标价2]\n\n"
    "📉 **风险提示：**\n"
    "[此处填写简洁的风险或应急计划]\n"
    "```\n\n"
    "--- \n*免责声明: 我是一个AI助手。所有内容不构成财务建议，所有交易均涉及风险。*"
)

if __name__ == '__main__':
    main()
