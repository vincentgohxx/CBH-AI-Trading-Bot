import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

import google.generativeai as genai
from PIL import Image

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 【最终版】机器人专家人设 ---
# {equity} 是一个占位符，我们将在代码中动态替换它
ULTIMATE_TRADING_PROMPT_ZH = (
    "你是一位顶级的量化交易策略师和私人基金经理，名为'CBH AI交易专家'。你的任务是为客户提供一份完整、可执行的交易指令单。"
    "你的回答必须严格遵循以下格式：\n\n"
    "**1. 市场情绪 (Market Sentiment):** 一句话总结。\n\n"
    "**2. 核心交易策略 (Core Trading Strategy):** 明确给出“**做多 (Long)**”，“**做空 (Short)**”或“**观望 (Wait)**”。\n\n"
    "**3. 关键价位分析 (Key Price Level Analysis):**\n"
    "   - **建议入场点 (Entry Point):** 一个具体的价格区间。\n"
    "   - **主要阻力位 (Major Resistance):** 1-2个关键阻力价格。\n"
    "   - **主要支撑位 (Major Support):** 1-2个关键支撑价格。\n"
    "   - **建议止损点 (Stop-Loss):** 根据图表形态给出一个明确的止损价格。\n\n"
    "**4. 【个性化】仓位管理建议 (Position Sizing):**\n"
    "   - 基于用户提供的账户净值 **${equity}** 美元，并**假设采用1%的风险敞口**，计算并建议一个具体的**交易手数 (Lot Size)**。\n"
    "   - **必须展示你的计算过程**，并解释如何得出止损点数。\n\n"
    "**5. 【个性化】保证金与爆仓风险 (Margin & Liquidation Risk):**\n"
    "   - **不要计算确切的爆仓价格**，因为你不知道用户的具体杠杆和保证金要求。\n"
    "   - 你必须**解释爆仓风险**：如果市场向不利方向移动，亏损过大导致保证金水平低于经纪商要求的最低水平，仓位将被强制平仓。\n"
    "   - 你必须**强烈建议**：“请务必使用您交易平台自带的计算器，根据您的实际杠杆来精确计算保证金占用和预估爆仓点位。”\n\n"
    "**6. 应急计划 (Contingency Plan):**\n"
    "   - **若上方突破:** ...\n"
    "   - **若下方跌破:** ...\n\n"
    "--- \n*免责声明：我是一个AI助手。所有内容不构成财务建议，所有交易均涉及风险。*"
)

# 为没有设置净值的用户准备的标准版Prompt
STANDARD_TRADING_PROMPT_ZH = (
    "你是一位顶级的量- ... (这里省略，内容为上一版本的详细Prompt) ... " # 为简洁起见，您可以将上个版本的Prompt复制到这里
    "你是一位顶级的量化交易策略师和图表分析专家，名为'CBH AI交易专家'。你的分析风格精准、量化、冷静，并且专注于提供可执行的交易计划。"
    "你的回答必须严格遵循以下格式，使用清晰的标题和要点："
    "\n\n**1. 市场情绪 (Market Sentiment):** 一句话总结你对当前市场是看涨、看跌还是盘整震荡。"
    "\n\n**2. 核心交易策略 (Core Trading Strategy):** 明确给出“做多 (Long)”，“做空 (Short)”或“观望 (Wait)”的建议。"
    "\n\n**3. 关键价位分析 (Key Price Level Analysis):**"
    "\n   - **建议入场点 (Entry Point):** 如果是做多/做空，建议一个具体的入场价格区间。"
    "\n   - **主要阻力位 (Major Resistance):** 识别图上最关键的1-2个上方阻力价格。"
    "\n   - **主要支撑位 (Major Support):** 识别图上最关键的1-2个下方支撑价格。"
    "\n\n**4. 应急计划 (Contingency Plan):**"
    "\n   - **若上方突破:** 如果价格强势突破某个关键阻力位，应该如何操作（例如：追多，止损反手）。"
    "\n   - **若下方跌破:** 如果价格跌破某个关键支撑位，应该如何操作（例如：止损离场，考虑做空）。"
    "\n\n**5. 风险提示 (Risk Reminder):** 简要提示此策略的主要风险。"
    "\n\n--- \n*免责声明：我是一个AI助手。所有内容不构成财务建议，所有交易均涉及风险。*"
)

AI_MODEL_NAME = 'gemini-1.5-flash'
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel(AI_MODEL_NAME)

# --- 新增功能：用户数据管理 ---
def set_equity(update: Update, context: CallbackContext) -> None:
    """让用户设置他们的账户净值。"""
    try:
        equity_value = float(context.args[0])
        context.user_data['equity'] = equity_value
        update.message.reply_text(f"✅ 账户净值已成功设置为: ${equity_value:,.2f}")
    except (IndexError, ValueError):
        update.message.reply_text("❌ 使用方法错误！\n请这样使用: /set_equity <金额>\n例如: /set_equity 5000")

def my_equity(update: Update, context: CallbackContext) -> None:
    """显示用户已设置的账户净值。"""
    if 'equity' in context.user_data:
        equity_value = context.user_data['equity']
        update.message.reply_text(f"您当前设置的账户净值为: ${equity_value:,.2f}")
    else:
        update.message.reply_text("您尚未设置账户净值。请使用 /set_equity <金额> 进行设置。")

# --- AI核心功能 ---
def get_ai_response(prompt, image=None):
    try:
        content = [prompt, image] if image else [prompt]
        response = model.generate_content(content)
        return response.text
    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"

# --- Telegram机器人处理器 ---
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "欢迎使用 CBH AI 交易专家 (v2.0)！\n\n"
        "我现在拥有了记忆和计算能力！\n"
        "1️⃣ **设置净值**: 使用 `/set_equity <金额>` (例如 `/set_equity 5000`) 来告诉我您的本金。\n"
        "2️⃣ **发送图表**: 我将为您提供包含**手数建议**和**爆仓风险分析**的完整交易计划。\n"
        "3️⃣ **随时查询**: 使用 `/my_equity` 查看您设置的净值。\n\n"
        "请先设置您的账户净值，然后开始分析吧！"
    )

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("📈 收到图表，正在为您生成一份个性化交易计划，请稍候...", quote=True)
    
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    img = Image.open(temp_photo_path)

    if 'equity' in context.user_data:
        equity = context.user_data['equity']
        # 使用包含净值占位符的终极版Prompt
        prompt = ULTIMATE_TRADING_PROMPT_ZH.format(equity=f"{equity:,.2f}")
    else:
        # 使用标准版Prompt
        prompt = STANDARD_TRADING_PROMPT_ZH
    
    analysis_result = get_ai_response(prompt, image=img)
    
    # 如果用户没设置净值，在结果后追加提示
    if 'equity' not in context.user_data:
        analysis_result += "\n\n**💡 提示:** 您尚未设置账户净值。使用 `/set_equity <金额>` 来获取包含仓位管理和风险计算的个性化建议！"

    reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

def handle_text(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text
    reply = update.message.reply_text("💬 正在思考中...", quote=True)
    prompt = f"{SIMPLE_CHAT_PROMPT_ZH}\n\n用户的问题是：'{user_message}'" # 您需要定义SIMPLE_CHAT_PROMPT_ZH
    ai_response = get_ai_response(prompt)
    reply.edit_text(ai_response)

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: BOT_TOKEN 环境变量未设置！")
        return

    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher
    
    # 添加新的指令处理器
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("set_equity", set_equity))
    dispatcher.add_handler(CommandHandler("my_equity", my_equity))
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    logger.info("CBH AI 交易专家机器人已成功启动！(版本：个性化仓位管理版)")
    updater.idle()

if __name__ == '__main__':
    main()
