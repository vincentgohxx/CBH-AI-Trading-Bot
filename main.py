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

# --- 【新增】机器人专家人设：斐波那契分析大师 ---
FIBONACCI_COACH_PROMPT_ZH = (
    "你是一位顶级的技术分析大师，名为'CBH AI交易专家'，尤其精通斐波那契数列在金融市场中的应用。你的任务是像一位大师级教练一样，教会用户如何运用斐波那契工具来解读市场。"
    "你的回答必须严格遵循以下格式，使用清晰的标题和要点:\n\n"
    "**1. 主要趋势分析 (Overall Trend Analysis):**\n"
    "   - 一句话总结图表所示的主要趋势是上升、下降还是盘整。\n\n"
    "**2. 斐波那契工具应用 (Fibonacci Tool Application):**\n"
    "   - **工具识别:** 指出图表中最适合应用的斐波那契工具是“回撤(Retracement)”还是“扩展(Extension)”。\n"
    "   - **锚点定义:** 清晰地说明斐波那契工具的锚点（起点和终点）应该画在哪个“波段高点(Swing High)”和“波段低点(Swing Low)”。例如：“此斐波那契回撤工具应从 [价格A] 的波段低点连接至 [价格B] 的波段高点。”\n\n"
    "**3. 关键斐波那契水平解读 (Key Fibonacci Levels):**\n"
    "   - 列出最重要的几个斐波那契水平位（例如: 0.382, 0.5, 0.618）。\n"
    "   - **专业解读:** 解释这些水平现在扮演的角色。例如：“0.618水平（价格约 XXXX）现在是本次回调的‘黄金支撑位’，是多头重点关注的区域。”\n\n"
    "**4. 关键水平共振分析 (Confluence Analysis):**\n"
    "   - **【高级分析】** 指出是否有任何斐波那契水平与其他技术指标（如移动平均线、前期支撑/阻力位）重合或接近。例如：“值得注意的是，0.5回撤位与图中的50周期移动平均线形成了‘共振支撑’，这大大增强了该水平的有效性。”\n\n"
    "**5. 教练总结与教学 (Coach's Summary & Lesson):**\n"
    "   - **核心教学点:** 总结本次分析的核心教学内容。例如：“本次分析的核心是学习如何在上升趋势中，利用斐波那契回撤来寻找潜在的、高概率的买入点。”\n"
    "   - **下一步观察:** 提示用户接下来应该重点观察价格在哪个关键斐波那契水平上的反应。\n\n"
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

FMP_API_KEY = os.getenv("FMP_API_KEY")

# --- 价格监控功能 (代码不变) ---
def get_gold_price():
    # ... (代码与上一版完全相同，此处省略以保持简洁)
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
    # ... (代码与上一版完全相同，此处省略以保持简洁)
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

def watch(update: Update, context: CallbackContext) -> None:
    # ... (代码与上一版完全相同，此处省略以保持简洁)
    chat_id = update.effective_chat.id
    try:
        condition = context.args[0]
        target_price = float(context.args[1])
        if condition not in ['>', '<']: raise ValueError()
        job_context = {'chat_id': chat_id, 'target_price': target_price, 'condition': condition}
        context.job_queue.run_repeating(check_prices, interval=300, first=0, context=job_context, name=f"watch_{chat_id}_{condition}_{target_price}")
        update.message.reply_text(f"✅ **监控已设置**\n当黄金价格 **{condition} ${target_price:,.2f}** 时，我会提醒您。")
    except (IndexError, ValueError):
        update.message.reply_text("❌ **指令格式错误！**\n请这样使用:\n`/watch > 2380`\n`/watch < 2300`")


# --- AI核心与图片处理 ---
def analyze_chart_with_fibonacci_coach(image_path: str) -> str:
    if not model: return "抱歉，AI服务未启动。"
    try:
        img = Image.open(image_path)
        # 【重要】使用全新的斐波那契教练指令
        prompt = f"{FIBONACCI_COACH_PROMPT_ZH}\n\n请严格按照以上格式，分析这张黄金图表，并提供斐波那契分析。"
        response = model.generate_content([prompt, img])
        return response.text
    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，AI教练当前不可用。错误: {e}"

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("收到图表，正在请我的斐波那契分析大师为您进行深度解读...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    # 调用新的分析函数
    analysis_result = analyze_chart_with_fibonacci_coach(temp_photo_path)
    reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

# --- 其他指令 ---
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "欢迎使用 CBH AI 斐波那契教练 & 哨兵 (v5.0)！\n\n"
        "我现在是您的私人斐波那契分析大师：\n"
        "1️⃣ **AI斐波那契教练**: 发送一张黄金图表，我将教您如何用斐波那契工具进行专业分析。\n"
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

    updater.start_polling()
    logger.info("CBH AI 斐波那契教练 & 哨兵机器人已成功启动！")
    updater.idle()

if __name__ == '__main__':
    main()
