import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from database.memory import MongoMemory
from rag_pipeline.retriever import RAGPipeline

logger = logging.getLogger(__name__)

# Load config
assistant_ids_str = os.getenv("ASSISTANT_USER_IDS", "")
ASSISTANT_USER_IDS = [int(id.strip()) for id in assistant_ids_str.split(",") if id.strip().isdigit()]

# Initialize singletons
memory = MongoMemory()
rag = RAGPipeline()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming text messages."""
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name
    text = update.message.text

    # 1. Log the incoming message to MongoDB
    memory.add_message(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        message=text,
        is_bot=False
    )

    # 2. Check if this is a reply from an Assistant
    if user_id in ASSISTANT_USER_IDS and update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        replied_user_id = replied_msg.from_user.id
        
        # We only learn if they are replying to a client's message
        if replied_user_id not in ASSISTANT_USER_IDS and replied_user_id != context.bot.id:
            question = replied_msg.text
            answer = text
            if question and answer:
                logger.info("Assistant replied to client. Learning Q&A pair...")
                rag.learn_qa_pair(question, answer)
        
        # Don't try to bot-respond to assistant messages
        return

    # 3. Determine if the bot should process this message.
    bot_username = context.bot.username
    is_group = update.message.chat.type in ['group', 'supergroup']
    
    should_respond = False
    
    if is_group:
        if bot_username and f"@{bot_username}" in text:
            should_respond = True
        elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
            should_respond = True
        elif "?" in text:
            should_respond = True
    else:
        # In private chat, process everything
        should_respond = True

    if not should_respond:
        return

    # Clean the bot's tag from the message for the query
    query = text.replace(f"@{bot_username}", "").strip() if bot_username else text
    
    # Process immediately
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        recent_history = memory.get_recent_history(chat_id=chat_id, minutes=5)
        
        answer = rag.answer_question(question=query, history=recent_history)
        
        # Silent Fallback: if answer is None, the bot doesn't know and should stay silent.
        if answer is None:
            logger.info("Bot is not confident in the answer. Staying silent.")
            return
            
        await update.message.reply_text(answer)
        
        memory.add_message(
            chat_id=chat_id,
            user_id=context.bot.id,
            username=bot_username or "Assistant",
            message=answer,
            is_bot=True
        )
    except Exception as e:
        logger.error(f"Error handling message: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    welcome_text = (
        "Assalomu alaykum! Men Keeping platformasinig yordamchi botiman. Men Keeping platformasidagi barcha hujjatlar va videolardan olingan bilim bazamizga asoslanib sizning savollargizga javob berishda yordam bera olaman. "
        "Meni shu chatdan turib savol berishgiz yoki istalgan gruppaga admin sifatida qo'shib qo'yishingiz mumkin."
    )
    await update.message.reply_text(welcome_text)
