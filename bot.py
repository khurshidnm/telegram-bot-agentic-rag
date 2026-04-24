import os
import logging
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot.handlers import (
    handle_message,
    handle_voice,
    handle_image,
    start_command,
    my_role_command,
    admin_help_command,
    kb_count_command,
    kb_list_command,
    kb_get_command,
    kb_add_command,
    kb_edit_command,
    kb_delete_command,
    kb_export_command,
    image_drafts_command,
    image_approve_command,
    image_reject_command,
    learning_drafts_command,
    learning_approve_command,
    learning_reject_command,
)

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def error_handler(update, context):
    """Logs unhandled Telegram update errors without crashing the polling loop."""
    logger.exception("Unhandled exception while processing update", exc_info=context.error)

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
    application.add_handler(CommandHandler("my_role", my_role_command))
    application.add_handler(CommandHandler("admin_help", admin_help_command))
    application.add_handler(CommandHandler("kb_count", kb_count_command))
    application.add_handler(CommandHandler("kb_list", kb_list_command))
    application.add_handler(CommandHandler("kb_get", kb_get_command))
    application.add_handler(CommandHandler("kb_add", kb_add_command))
    application.add_handler(CommandHandler("kb_edit", kb_edit_command))
    application.add_handler(CommandHandler("kb_delete", kb_delete_command))
    application.add_handler(CommandHandler("kb_export", kb_export_command))
    application.add_handler(CommandHandler("image_drafts", image_drafts_command))
    application.add_handler(CommandHandler("image_approve", image_approve_command))
    application.add_handler(CommandHandler("image_reject", image_reject_command))
    application.add_handler(CommandHandler("learning_drafts", learning_drafts_command))
    application.add_handler(CommandHandler("learning_approve", learning_approve_command))
    application.add_handler(CommandHandler("learning_reject", learning_reject_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.Document.IMAGE, handle_image))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    # Start the Bot
    logger.info("Bot is polling...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
