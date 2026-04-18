import os
import logging
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot.handlers import handle_message, start_command

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN is not set in the environment.")
        return

    logger.info("Starting bot application...")
    
    # Build the application
    application = ApplicationBuilder().token(token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    logger.info("Bot is polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
