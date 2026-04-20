import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from database.memory import MongoMemory
from rag_pipeline.retriever import RAGPipeline
from config.admins import admin_manager

logger = logging.getLogger(__name__)

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
    is_admin = admin_manager.is_admin(user_id)

    # 1. Log the incoming message to MongoDB (admins included)
    memory.add_message(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        message=text,
        is_bot=False
    )

    # 2. Handle admin messages: learn from their interactions but don't reply
    if is_admin:
        # If an admin is replying to a client's message, learn from it
        if update.message.reply_to_message:
            replied_msg = update.message.reply_to_message
            replied_user_id = replied_msg.from_user.id
            
            # Learn from admin's reply to client questions
            if not admin_manager.is_admin(replied_user_id) and replied_user_id != context.bot.id:
                question = replied_msg.text
                answer = text
                if question and answer:
                    logger.info(f"Admin {username} replied to client. Learning Q&A pair...")
                    rag.learn_qa_pair(question, answer)
        
        # Don't respond to admin messages - admins are support staff, not clients
        logger.info(f"Admin {username} sent message, skipping bot response")
        return

    # 3. Check if this is a reply from another bot/assistant (non-admin)
    if update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        replied_user_id = replied_msg.from_user.id
        
        # Learn if they are replying to a client's message (and not from bot itself)
        if not admin_manager.is_admin(replied_user_id) and replied_user_id != context.bot.id:
            question = replied_msg.text
            answer = text
            if question and answer:
                logger.info("User replied to question. Learning Q&A pair...")
                rag.learn_qa_pair(question, answer)

    # 4. Determine if the bot should process this message.
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
        "👋 Assalomu alaykum!\n\n"
        "Men — Keeping platformasi rasmiy yordamchi botiman 🤖\n\n"
        "📚 Nima qila olaman?\n"
        "Keeping platformasidagi barcha hujjatlar va videolar asosida tayyorlangan bilim bazasidan foydalanib, "
        "sizning savollaringizga aniq va tezkor javob beraman.\n\n"
        "💬 Qanday foydalanish mumkin?\n"
        "• Shu chatda bevosita savol bering\n"
        "• Yoki meni istalgan guruhga 'admin' sifatida qo'shing\n\n"
        "❓ Savolingiz bormi? Bemalol yozing — men shu yerdaman!"
    )
    await update.message.reply_text(welcome_text)
