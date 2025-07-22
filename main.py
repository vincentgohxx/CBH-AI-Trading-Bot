import os
import logging
import signal  # 导入信号处理模块
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests
from openai import OpenAI # 导入OpenAI的库
import base64            # 导入用于图片编码的工具
from PIL import Image
from functools import wraps



logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 【最终版】机器人专家人设：系统交易员 ---
MVP_ANALYST_PROMPT_ZH = (
    "你是一位顶级的量化交易策略师，名为'CBH AI交易专家'，其核心交易哲学是“只参与高胜率和高风险报酬比的交易”。\n\n"
    "你的分析和推荐必须严格遵循以下【交易纪律】:\n"
    "1. **止损纪律:** 你的止损设置必须非常严格，理想情况下应控制在**10-15个点（pips）**左右，以实现最佳的风险控制。\n"
    "2. **盈亏比铁律:** 你推荐的任何策略，其**风险报酬比必须大于或等于 1:1.5**。这意味着，你的**“目标价(Take Profit)”与“入场点”的距离，必须至少是“止损点(Stop Loss)”与“入场点”距离的1.5倍**。\n"
    "3. **观望原则:** 如果根据当前图表，**无法找到**满足以上两条纪律的合理交易机会，你的核心策略**必须**明确推荐“**观望 (Wait)**”，并解释为何当前市场结构不满足你的交易纪律。\n\n"
    "在遵循以上纪律的前提下，你的回答必须严格、完全地遵循以下格式:\n\n"
    "```\n"
    "📊 **分析结果（[交易符号 H_]）**\n\n"
    "📈 **趋势：** [简洁分析 + 技术原因]\n\n"
    "📌 **支撑位：** [价格1] / [价格2]\n"
    "📌 **阻力位：** [价格1] / [价格2]\n\n"
    "🎯 **推荐操作（必须满足1:1.5+盈亏比）：**\n"
    "[做多/做空/观望]（[入场条件]） → **止损设** [止损价格] → **目标价：** [目标价1] / [目标价2]\n\n"
    "📉 **风险提示：**\n"
    "[简洁的风险或应急计划]\n"
    "```\n\n"
    "--- \n*免责声明: 我是一个AI助手。所有内容不构成财务建议，所有交易均涉及风险。*"
)

# --- 核心配置 (OpenAI) ---
AI_MODEL_NAME = 'gpt-4o'
try:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = OpenAI(api_key=api_key)
    else:
        logger.critical("环境变量 OPENAI_API_KEY 未设置！")
        client = None
except Exception as e:
    logger.critical(f"OpenAI 客户端初始化失败: {e}")
    client = None

FMP_API_KEY = os.getenv("FMP_API_KEY")

# 【重要】将 updater 设为全局变量，以便在 shutdown 函数中访问
updater = None

# --- 函数定义 ---

def get_price(symbol: str) -> dict:
    if not FMP_API_KEY:
        return {"error": "行情服务未配置。"}
    formatted_symbol = symbol.upper()
    if len(symbol) == 6 and symbol not in ["GOLD", "SILVER"]:
        formatted_symbol = f"{symbol[:3]}/{symbol[3:]}"
    url = f"https://financialmodelingprep.com/api/v3/quote/{formatted_symbol}?apikey={FMP_API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data:
            return {
                "name": data[0].get("name", symbol),
                "price": data[0].get("price"),
                "change": data[0].get("change", 0),
                "changesPercentage": data[0].get("changesPercentage", 0)
            }
        return {"error": f"找不到交易对 {symbol} 的数据。"}
    except requests.RequestException as e:
        logger.error(f"获取 {symbol} 价格时出错: {e}")
        return {"error": "获取行情失败，请稍后再试。"}

def analyze_chart(image_path: str) -> str:
    if not client:
        return "抱歉，AI服务因配置问题未能启动。"

    try:
        # 1. 读取图片文件
        with open(image_path, "rb") as image_file:
            # 2. 将图片编码为Base64格式，这是OpenAI API要求的
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # 3. 调用OpenAI的gpt-4o模型进行分析
        logger.info(f"正在使用模型 {AI_MODEL_NAME} 分析图表...")
        response = client.chat.completions.create(
            model=AI_MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": MVP_ANALYST_PROMPT_ZH # 我们继续使用那个强大的指令
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500 # 限制一下回复长度
        )
        
        analysis_result = response.choices[0].message.content
        return analysis_result.replace("```", "").strip()

    except Exception as e:
        logger.error(f"调用OpenAI API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "欢迎使用 CBH AI 交易助手 (v2.0 - GOD)！\n\n"
        "**核心功能:**\n"
        "1️⃣ **AI图表分析**\n"
        "2️⃣ **实时行情**: 使用 `/price <交易对>` 查询。\n\n"
        "我们开始吧！"
    )

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("收到图表，正在为您生成一份符合交易纪律的专业信号，请稍候...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    analysis_result = analyze_chart(temp_photo_path)
    try:
        reply.edit_text(analysis_result, parse_mode='Markdown')
    except Exception:
        reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

def price_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("❌ **指令格式错误！**\n请提供一个交易对，例如: `/price XAUUSD`")
        return
    symbol = context.args[0].upper()
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

def shutdown(signum, frame):
    """一个处理关机信号的函数，用于实现优雅退场。"""
    logger.info("收到关机信号... 正在优雅地关闭机器人...")
    if updater:
        updater.stop()
        updater.is_idle = False
    logger.info("机器人已成功关闭。")

def main() -> None:
    global updater

    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return

    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher
    
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("price", price_command))
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    
    # 注册信号处理器，实现优雅退场
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    updater.start_polling()
    logger.info("CBH AI 交易助手 已成功启动！")
    updater.idle()

if __name__ == '__main__':
    main()
