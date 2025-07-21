import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# 导入AI开发包
import google.generativeai as genai
from PIL import Image

# 设置日志
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- 【终极版】机器人专家人设 (中文版) ---
# 这个指令将指导AI生成一个完整的、可执行的交易计划。
EXPERT_TRADING_PROMPT_ZH = (
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

# 为普通聊天准备一个简化版的人设
SIMPLE_CHAT_PROMPT_ZH = (
    "你是一位名为'CBH AI交易专家'的资深AI助手，精通外汇交易领域。你总是以专业、自信且乐于助人的口吻，"
    "回答用户关于交易的通用问题。"
    "在你的每一条回复的结尾，都必须另起一行附上以下免责声明："
    "--- \n*免责声明：我是一个AI助手。所有内容不构成财务建议，所有交易均涉及风险。*"
)

# --- 统一使用最新的AI模型 ---
AI_MODEL_NAME = 'gemini-1.5-flash'


# --- AI视觉与聊天功能 ---

def analyze_chart_with_gemini(image_path: str) -> str:
    logger.info(f"正在使用模型 {AI_MODEL_NAME} 分析图表...")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "错误：服务器端的AI分析功能未配置。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(AI_MODEL_NAME)
        img = Image.open(image_path)
        
        # 【优化】在分析图片时，我们使用全新的、详细的交易计划指令
        prompt_for_image = f"{EXPERT_TRADING_PROMPT_ZH}\n\n请严格按照以上格式，分析这张图表。"
        
        response = model.generate_content([prompt_for_image, img])
        return response.text

    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"


def chat_with_gemini(user_text: str) -> str:
    logger.info(f"正在使用模型 {AI_MODEL_NAME} 处理文字问题: '{user_text}'")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "错误：AI聊天功能未配置。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(AI_MODEL_NAME)
        
        # 【优化】在处理普通文字聊天时，我们使用简化版人设
        full_prompt = f"{SIMPLE_CHAT_PROMPT_ZH}\n\n用户的问题是：'{user_text}'"

        response = model.generate_content(full_prompt)
        return response.text

    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，我的AI大脑暂时无法连接。错误: {e}"


# --- Telegram机器人处理器 ---

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "欢迎使用 CBH AI 交易专家！\n\n"
        "作为一名专业的AI交易助手，我可以：\n"
        "📈 **分析图表**：发送任何交易图表照片给我，我将为您提供一份详细的交易计划。\n"
        "💬 **探讨策略**：向我询问任何关于外汇、交易策略或市场分析的问题。\n\n"
        "今天我能如何协助您？"
    )

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("📈 收到图表，正在为您生成一份详细的交易计划，请稍候...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    analysis_result = analyze_chart_with_gemini(temp_photo_path)
    reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

def handle_text(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text
    reply = update.message.reply_text("💬 正在思考中...", quote=True)
    ai_response = chat_with_gemini(user_message)
    reply.edit_text(ai_response)

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return

    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    logger.info("CBH AI 交易专家机器人已成功启动！(版本：终极策略版)")
    updater.idle()


if __name__ == '__main__':
    main()
