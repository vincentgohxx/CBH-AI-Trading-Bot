import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

import google.generativeai as genai
from PIL import Image

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 【最终版】机器人专家人设 ---
ULTIMATE_TRADING_PROMPT_ZH = (
    "你是一位顶级的量化交易策略师和私人基金经理... (内容与上一版相同)"
)
STANDARD_TRADING_PROMPT_ZH = (
    "你是一位顶级的量化交易策略师和图表分析专家... (内容与上一版相同)"
)
SIMPLE_CHAT_PROMPT_ZH = (
    "你是一位名为'CBH AI交易专家'的资深AI助手... (内容与上一版相同)"
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

# --- 【新增】金融计算核心配置 ---
LEVERAGE = 1000  # 杠杆比例 1:1000
STOP_OUT_LEVEL_PERCENT = 0.50  # 强制平仓水平，假设为50%
# 不同交易品种的合约大小（每1标准手）
CONTRACT_SIZES = {
    "XAUUSD": 100,      # 黄金: 100盎司
    "EURUSD": 100000,   # 欧元/美元: 100,000欧元
    "GBPUSD": 100000,   # 英镑/美元: 100,000英镑
    "USDJPY": 100000,   # 美元/日元: 100,000美元
    # 您可以在这里添加更多您常交易的品种
}

# --- 新增功能: 风险计算器 ---
def calculate_risk(update: Update, context: CallbackContext) -> None:
    """计算预付款和预估爆仓价。"""
    # 1. 检查用户是否已设置净值
    if 'equity' not in context.user_data:
        update.message.reply_text("❌ **计算失败**\n请先使用 `/set_equity <金额>` 设置您的账户净值。")
        return

    # 2. 检查指令格式是否正确
    if len(context.args) != 3:
        update.message.reply_text(
            "❌ **指令格式错误！**\n请这样使用:\n`/calc <交易对> <手数> <当前价格>`\n\n"
            "**例如:**\n`/calc XAUUSD 0.1 2350.50`"
        )
        return

    try:
        # 3. 解析用户输入
        pair = context.args[0].upper()
        lot_size = float(context.args[1])
        current_price = float(context.args[2])
        equity = float(context.user_data['equity'])

        # 4. 检查交易对是否受支持
        if pair not in CONTRACT_SIZES:
            supported_pairs = ", ".join(CONTRACT_SIZES.keys())
            update.message.reply_text(f"❌ **交易对不支持**\n目前仅支持: {supported_pairs}")
            return

        # 5. 开始核心计算
        contract_size = CONTRACT_SIZES[pair]
        
        # 计算开仓需要的预付款（保证金）
        margin_required = (contract_size * lot_size * current_price) / LEVERAGE

        # 如果保证金超过净值，无法开仓
        if margin_required > equity:
            update.message.reply_text(
                f"❌ **保证金不足！**\n\n"
                f"开仓所需预付款: `${margin_required:,.2f}`\n"
                f"您的账户净值: `${equity:,.2f}`\n\n"
                "无法开仓，请减少手数。"
            )
            return
        
        # 计算强制平仓时账户的剩余资金
        stop_out_equity = margin_required * STOP_OUT_LEVEL_PERCENT
        # 计算账户能承受的最大亏损金额
        max_loss_allowed = equity - stop_out_equity

        # 计算价格波动多少会导致爆仓
        # 对于黄金(XAUUSD)，价格每波动$1，1标准手的盈亏是$100
        # 对于外汇(EURUSD等)，价格每波动1个点(0.0001)，1标准手的盈亏是$10
        if pair == "XAUUSD":
            # 价格波动 = 总亏损 / (手数 * 每手每美元价值)
            price_change_to_liquidate = max_loss_allowed / (lot_size * 100)
        else: # 假设为标准外汇对
            # 点数波动 = 总亏损 / (手数 * 每手每点价值)
            pips_to_liquidate = max_loss_allowed / (lot_size * 10)
            price_change_to_liquidate = pips_to_liquidate * 0.0001
        
        # 计算预估爆仓价格
        liquidation_price_long = current_price - price_change_to_liquidate
        liquidation_price_short = current_price + price_change_to_liquidate

        # 6. 生成并发送结果报告
        response_text = (
            f"**⚙️ 风险计算报告**\n\n"
            f"**输入参数:**\n"
            f"- 账户净值: `${equity:,.2f}`\n"
            f"- 交易对: `{pair}`\n"
            f"- 手数: `{lot_size}`\n"
            f"- 当前价格: `${current_price:,.2f}`\n\n"
            f"**计算假设:**\n"
            f"- 杠杆: `1:{LEVERAGE}`\n"
            f"- 强制平仓水平: `{STOP_OUT_LEVEL_PERCENT:.0%}`\n\n"
            f"**计算结果:**\n"
            f"🔹 **开仓所需预付款:** `${margin_required:,.2f}`\n\n"
            f"**🚨 预估爆仓价格:**\n"
            f"   - 如果**做多(Buy)**, 预估爆仓价: **`${liquidation_price_long:,.2f}`**\n"
            f"   - 如果**做空(Sell)**, 预估爆仓价: **`${liquidation_price_short:,.2f}`**\n\n"
            f"--- \n"
            f"*免责声明: 此为理论估算值，未考虑隔夜利息和点差。实际爆仓价格请以您的交易平台为准。*"
        )
        update.message.reply_text(response_text, parse_mode='Markdown')

    except (ValueError):
        update.message.reply_text("❌ **输入错误！**\n手数和价格必须为数字。")


# --- 其他所有函数 (start, set_equity, my_equity, get_ai_response, handle_photo, handle_text) ---
# ... (这里省略所有旧函数的代码，它们无需任何修改，保持原样即可) ...
# 为了让代码块完整，我还是把它们都贴出来
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "欢迎使用 CBH AI 交易专家 (v3.0)！\n\n"
        "我已进化为您的私人风险计算器！\n"
        "1️⃣ **设置净值**: 使用 `/set_equity <金额>` (例如 `/set_equity 5000`)。\n"
        "2️⃣ **风险计算**: 使用 `/calc <交易对> <手数> <价格>` (例如 `/calc XAUUSD 0.1 2350`) 来计算爆仓点。\n"
        "3️⃣ **AI分析**: 发送图表，获取包含手数建议的交易计划。\n\n"
        "请开始使用吧！"
    )

def set_equity(update: Update, context: CallbackContext) -> None:
    try:
        equity_value = float(context.args[0])
        context.user_data['equity'] = equity_value
        update.message.reply_text(f"✅ 账户净值已成功设置为: ${equity_value:,.2f}")
    except (IndexError, ValueError):
        update.message.reply_text("❌ 使用方法错误！\n请这样使用: /set_equity <金额>\n例如: /set_equity 5000")

def my_equity(update: Update, context: CallbackContext) -> None:
    if 'equity' in context.user_data:
        equity_value = context.user_data['equity']
        update.message.reply_text(f"您当前设置的账户净值为: ${equity_value:,.2f}")
    else:
        update.message.reply_text("您尚未设置账户净值。请使用 /set_equity <金额> 进行设置。")

def get_ai_response(prompt, image=None):
    if not model:
        return "抱歉，AI服务因配置问题未能启动，请联系管理员查看日志。"
    try:
        content = [prompt, image] if image else [prompt]
        response = model.generate_content(content)
        return response.text
    except Exception as e:
        logger.error(f"调用Gemini API时出错: {e}")
        return f"抱歉，AI分析师当前不可用。错误: {e}"

def handle_photo(update: Update, context: CallbackContext) -> None:
    reply = update.message.reply_text("📈 收到图表，正在为您生成一份个性化交易计划，请稍候...", quote=True)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    
    try:
        img = Image.open(temp_photo_path)
    except Exception as e:
        logger.error(f"无法打开图片: {e}")
        reply.edit_text("❌ 抱歉，无法处理您发送的图片文件。")
        os.remove(temp_photo_path)
        return

    if 'equity' in context.user_data:
        equity = context.user_data['equity']
        prompt = ULTIMATE_TRADING_PROMPT_ZH.format(equity=f"{equity:,.2f}")
    else:
        prompt = STANDARD_TRADING_PROMPT_ZH
    
    analysis_result = get_ai_response(prompt, image=img)
    
    if 'equity' not in context.user_data:
        analysis_result += "\n\n**💡 提示:** 您尚未设置账户净值。使用 `/set_equity <金额>` 来获取包含仓位管理和风险计算的个性化建议！"

    reply.edit_text(analysis_result)
    os.remove(temp_photo_path)

def handle_text(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text
    reply = update.message.reply_text("💬 正在思考中...", quote=True)
    prompt = f"{SIMPLE_CHAT_PROMPT_ZH}\n\n用户的问题是：'{user_message}'"
    ai_response = get_ai_response(prompt)
    reply.edit_text(ai_response)

def main() -> None:
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("致命错误: 环境变量 BOT_TOKEN 未设置！")
        return

    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher
    
    # 【重要】添加新的计算器指令处理器
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("set_equity", set_equity))
    dispatcher.add_handler(CommandHandler("my_equity", my_equity))
    dispatcher.add_handler(CommandHandler("calc", calculate_risk)) # 新增的指令
    
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    logger.info("CBH AI 交易专家机器人已成功启动！(版本: 风险计算器版)")
    updater.idle()

if __name__ == '__main__':
    main()
