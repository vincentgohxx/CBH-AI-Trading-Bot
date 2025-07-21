import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from PIL import Image

# Setup logging to see bot's activity, very useful on Render
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Core Analysis Logic ---
def analyze_chart_simple(image_path: str) -> str:
    """
    Provides a simple trading suggestion by analyzing red/green distribution 
    on the right side of the chart image.
    """
    try:
        with Image.open(image_path) as img:
            img = img.convert('RGB')
            width, height = img.size

            # --- Define Region of Interest (ROI) ---
            # We only care about the most recent trend, so we analyze the rightmost 25% of the image.
            roi_left = width * 0.75
            roi_top = 0
            roi_right = width
            roi_bottom = height
            
            roi = img.crop((roi_left, roi_top, roi_right, roi_bottom))

            # --- Color Analysis ---
            green_pixels = 0
            red_pixels = 0

            for pixel in roi.getdata():
                r, g, b = pixel
                # Check for significant green (G > R and G > B)
                # We add a threshold to avoid noise from white/grey backgrounds
                if g > r + 20 and g > b + 20 and g > 50:
                    green_pixels += 1
                # Check for significant red (R > G and R > B)
                elif r > g + 20 and r > b + 20 and r > 50:
                    red_pixels += 1
            
            logger.info(f"Analysis result: Green pixels={green_pixels}, Red pixels={red_pixels}")

            # --- Decision Making ---
            # Set a threshold to make the decision more robust.
            # We'll only make a call if the dominant color covers at least 1% of the area.
            threshold = (roi.width * roi.height) * 0.01

            if green_pixels > red_pixels and (green_pixels - red_pixels) > threshold:
                return "📈 **Suggestion: BUY**\nAnalysis: Recent trend appears bullish."
            elif red_pixels > green_pixels and (red_pixels - green_pixels) > threshold:
                return "📉 **Suggestion: SELL**\nAnalysis: Recent trend appears bearish."
            else:
                return "⚖️ **Suggestion: HOLD**\nAnalysis: The trend is unclear or the market is consolidating."

    except Exception as e:
        logger.error(f"An error occurred during image analysis: {e}")
        return "Sorry, an error occurred while analyzing the image. Please try again."


# --- Telegram Bot Handlers ---
def start(update: Update, context: CallbackContext) -> None:
    """Sends a welcome message when the /start command is issued."""
    update.message.reply_text(
        "Welcome to CBH AI Trading Bot!\n\n"
        "Please send a chart image (e.g., from MT5), and I will analyze it for you."
    )

def handle_photo(update: Update, context: CallbackContext) -> None:
    """Handles photo messages by downloading and analyzing them."""
    # Acknowledge receipt of the photo immediately
    reply = update.message.reply_text("Received chart. Analyzing, please wait...", quote=True)

    # Download the photo (highest resolution available)
    photo_file = update.message.photo[-1].get_file()
    temp_photo_path = f"{photo_file.file_id}.jpg"
    photo_file.download(temp_photo_path)
    logger.info(f"Image downloaded to: {temp_photo_path}")

    # Call the analysis function
    analysis_result = analyze_chart_simple(temp_photo_path)

    # Edit the original "Analyzing..." message to show the final result
    reply.edit_text(analysis_result, parse_mode='Markdown')

    # Clean up by deleting the temporary file
    try:
        os.remove(temp_photo_path)
        logger.info(f"Temporary file deleted: {temp_photo_path}")
    except OSError as e:
        logger.error(f"Error deleting temporary file: {e}")


def main() -> None:
    """Starts the bot."""
    # --- Load API Keys from Environment Variables ---
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.critical("FATAL ERROR: BOT_TOKEN environment variable is not set!")
        return
        
    currency_api_key = os.getenv("CURRENCY_API_KEY")
    if currency_api_key:
        logger.info("CURRENCY_API_KEY loaded successfully (ready for future use).")
    else:
        logger.warning("CURRENCY_API_KEY is not set. Features requiring it will be unavailable.")

    # --- Initialize Bot ---
    updater = Updater(bot_token, use_context=True)
    dispatcher = updater.dispatcher

    # Register handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.photo, handle_photo))

    # Start the Bot
    updater.start_polling()
    logger.info("Bot has started successfully!")

    # Run the bot until you press Ctrl-C
    updater.idle()


if __name__ == '__main__':
    main()
