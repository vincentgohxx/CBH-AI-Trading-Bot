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


# --- 机器人专家人设 (中文版) ---
# 在这里定义机器人的性格和行为准则，方便日后修改
EXPERT_PERSONA_PROMPT_ZH = (
    "你是一位名为'CBH AI交易专家'的资深AI助手，精通外汇交易领域。你总是以专业、自信且乐于助人的口吻，"
    "提供富有洞察力的分析，解释交易策略，并探讨市场趋势。"
    "重要提示：在你的每一条回复的结尾，都必须另起一行附上以下免责声明："
    "--- \n*免责声明：我是一个AI助手。所有内容不构成财务建议，所有交易均涉及风险。*"
)


# --- AI视觉与聊天功能 ---

def analyze_chart_with_gemini(image_path: str) -> str:
    """使用Google Gemini视觉模型分析图表照片。"""
    logger.info("正在使用Google Gemini视觉模型分析图表...")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("环境变量 GOOGLE_API_KEY 未设置！")
        return "错误：服务器端的AI分析功能未配置。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro-vision')
        img = Image.open(image_path)
        
        # 将专家人设与具体任务指令结合
        prompt = (
            f"{EXPERT_PERSONA_PROMPT_ZH}\n\n"
            "现在，请专门分析附上的这张金融图表。请仅根据图中的视觉信息（如K线、趋势线、指标等），"
            "给出一个清晰的交易建议（买入、卖出 或 观望），并附上简短的理由。"
        )
        
        response = model.generate_content([prompt, img])
        analysis_result = response.text
        logger.info(f"从Gemini收到的分析结果: {analysis_result}")
        return analysis_result

    except Exception as e:
        logger.error(f"调用Gemini视觉API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"


def chat_with_gemini(user_text: str) -> str:
    """使用Google Gemini Pro模型处理文字对话。"""
    logger.info(f"正在使用Gemini Pro处理文字问题: '{user_text}'")
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return "错误：AI聊天功能未配置。"

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        # 将专家人设与用户的具体问题结合
        full_prompt = f"{EXPERT_PERSONA_PROMPT_ZH}\n\n用户的问题是：'{user_text}'"

        response = model.generate_content(full_prompt)
        chat_reply = response.text
        logger.info(f"从Gemini收到的聊天回复: {chat_reply}")
        return chat_reply

    except Exception as e:
        logger.error(f"调用Gemini Pro API时出错: {e}")
        return f"抱歉，我的AI大脑暂时无法连接。错误: {e}"


# --- Telegram机器人处理器 ---

def start(update: Update, context: CallbackContext) -> None:
    """发送欢迎语和使用说明。"""
    update.message.reply_text(
        "欢迎使用 CBH AI 交易专家！\n\n"
        "作为一名专业的AI交易助手，我可以：\n"
        "📈 **分析图表**：发送任何交易图表照片给我。\n"
        "💬 **探讨策略**：向我询问任何关于外汇、交易策略或市场分析的问题。\n\n"
        "今天我能如何协助您？"
    )

def handle_photo(update: Update, context: CallbackContext) -> None:
    """处理图片消息，用于图表分析。"""
    reply = update.message.reply_text("📈 已收到图表。正在用我的AI视觉进行分析，请稍候...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    
    analysis_result = analyze_chart_with_gemini(temp_photo_path)
    
    reply.edit_text(analysis_result, parse_mode='Markdown')
    os.remove(temp_photo_path)


def handle_text(update: Update, context: CallbackContext) -> None:
    """处理所有非指令的文本消息，用于对话。"""
    user_message = update.message.text
    reply = update.message.reply_text("💬 正在思考中...", quote=True)
    
    ai_response = chat_with_gemini(user_message)
    
    reply.edit_text(ai_response, parse_mode='Markdown')


def main() -> None:
    """启动机器人。"""
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
    logger.info("CBH AI 交易专家机器人已成功启动！")
    updater.idle()


if __name__ == '__main__':
    main()
