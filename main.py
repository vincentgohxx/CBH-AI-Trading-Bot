import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

import requests
import google.generativeai as genai
from PIL import Image
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 【新】机器人专家人设：交易策略教练 ---
COACH_PROMPT_ZH = (
    "你是一位顶级的图表形态分析教练，名为'CBH AI交易专家'。你的任务不是给出直接的买卖指令，而是像一位教练一样，教会用户如何分析图表。"
    "你的回答必须严格遵循以下格式：\n\n"
    "**1. 主要形态识别 (Pattern Recognition):**\n"
    "   - 在这张图表中，我识别出了一个潜在的 **[形态名称]**，例如“上升三角形”、“头肩底”或“双顶”。\n\n"
    "**2. 形态解读 (Pattern Interpretation):**\n"
    "   - **这是什么？** 简单解释这个形态在技术分析中的意义（例如：这是一个持续形态，还是一个反转形态？）。\n"
    "   - **关键位置:** 识别并指出这个形态的关键点，例如“颈线位于...”，“上轨压力线位于...”。\n\n"
    "**3. 教科书式策略 (Textbook Strategy):**\n"
    "   - **确认信号:** 教学员如何确认这个形态的有效性（例如：等待价格放量突破并收盘在颈线上方）。\n"
    "   - **潜在入场点:** 根据教科书理论，建议一个理想的入场时机。\n"
    "   - **理论止损点:** 教学员通常会将止损设置在哪个关键位置下方/上方。\n\n"
    "**4. 当前状态评估 (Current Status):**\n"
    "   - 评估目前价格正处于形态的哪个阶段，并强调“该形态目前尚未完全确认，建议保持观察。”\n\n"
    "--- \n*免责声明: 我是一个AI教练，旨在提供教育内容。所有内容不构成财务建议，所有交易均涉及风险。*"
)

# --- 核心配置 ---
AI_MODEL_NAME = 'gemini-1.5-flash'
model = None
try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    model = genai.GenerativeModel(AI_MODEL_NAME)
except Exception as e:
    logger.critical(f"Google AI 初始化失败: {e}")

# --- 【新增】价格监控功能 ---
FMP_API_KEY = os.getenv("FMP_API_KEY")

def get_gold_price():
    if not FMP_API_KEY:
        logger.error("FMP_API_KEY 未设置！价格监控功能无法运行。")
        return None
    url = f"https://financialmodelingprep.com/api/v3/quote/XAUUSD?apikey={FMP_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        if data and 'price' in data[0]:
            return data[0]['price']
    except requests.RequestException as e:
        logger.error(f"获取黄金价格时出错: {e}")
    return None

def check_prices(context: CallbackContext):
    """定时任务，检查所有监控的价格。"""
    job = context.job
    chat_id = job.context['chat_id']
    target_price = job.context['target_price']
    condition = job.context['condition']
    
    current_price = get_gold_price()
    if current_price is None:
        return # 如果获取价格失败则跳过此次检查

    logger.info(f"检查价格: 当前={current_price}, 目标={target_price}, 条件={condition}")

    alert = False
    if condition == '>' and current_price > target_price:
        alert = True
    elif condition == '<' and current_price < target_price:
        alert = True

    if alert:
        text = (f"**🚨 价格警报: 黄金 (XAUUSD) 🚨**\n\n"
                f"您设置的条件 **(价格 {condition} {target_price})** 已满足！\n\n"
                f"**当前价格: ${current_price:,.2f}**")
        context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        job.schedule_removal() # 发送提醒后，移除此任务

def watch(update: Update, context: CallbackContext) -> None:
    """设置一个价格监控。用法: /watch < > <价格>"""
    chat_id = update.effective_chat.id
    try:
        condition = context.args[0]
        target_price = float(context.args[1])
        if condition not in ['>', '<']:
            raise ValueError()

        job_context = {'chat_id': chat_id, 'target_price': target_price, 'condition': condition}
        context.job_queue.run_repeating(check_prices, interval=300, first=0, context=job_context, name=f"watch_{chat_id}_{condition}_{target_price}")

        update.message.reply_text(f"✅ **监控已设置**\n当黄金价格 **{condition} ${target_price:,.2f}** 时，我会提醒您。")

    except (IndexError, ValueError):
        update.message.reply_text("❌ **指令格式错误！**\n请这样使用:\n`/watch > 2380`\n`/watch < 2300`")

# --- AI核心与图片处理 ---
def analyze_chart_with_coach(image_path: str) -> str:
    if not model: return "抱歉，AI服务未启动。"
    try:
        img = Image.open(image_path)
        prompt = f"{COACH_PROMPT_ZH}\n\n请严格按照以上格式，分析这张黄金图表。"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，AI教练当前不可用。错误: {e}"

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("收到图表，正在请我的AI教练为您进行形态分析...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    analysis_result = analyze_chart_with_coach(temp_photo_path)
    reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

# --- 其他指令 ---
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "欢迎使用 CBH AI 交易教练 & 哨兵 (v4.0)！\n\n"
        "我现在是您的私人教练和市场哨兵：\n"
        "1️⃣ **AI教练**: 发送一张黄金图表，我会教您识别里面的技术形态和策略。\n"
        "2️⃣ **价格哨兵**: 使用 `/watch <或> <价格>` 设置价格提醒。\n   例如: `/watch > 2380`\n\n"
        "我们开始吧！"
    )

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return

    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("watch", watch))
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    # 我们可以暂时禁用文字聊天，专注于核心功能
    # dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    logger.info("CBH AI 交易教练 & 哨兵机器人已成功启动！")
    updater.idle()

if __name__ == '__main__':
    main()
