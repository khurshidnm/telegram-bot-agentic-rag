import os
import logging
import re
from io import BytesIO
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

PAYMENT_ESCALATION_REPLY = (
    "Ассалому алайкум! Тўловингиз одатда бир неча дақиқа ичида кўринади. "
    "Агар бирон-бир муаммо юзага келса ёки тўлов кўринмаса, илтимос, "
    "@keepingmanager Telegram манзилига тўлов чекини юборишинг, текшириб берамиз."
)

GROUP_SUPPORT_ESCALATION = (
    "Илтимос, @keepingmanager Telegram манзилига юборинг."
)

ADMIN_HELP_TEXT = (
    "Admin Knowledge Commands:\n"
    "/kb_count - Show total knowledge entries\n"
    "/kb_list [page_size] [offset] - List entries with IDs\n"
    "/kb_get <id> - Show one entry\n"
    "/kb_add <question> | <answer> - Add Q&A pair\n"
    "/kb_edit <id> | <question> | <answer> - Update entry\n"
    "/kb_delete <id> - Delete entry\n"
    "/kb_export - Export all entries as a text file\n"
    "/admin_help - Show this help"
)


def _is_private_chat(update: Update) -> bool:
    return bool(update.message and update.message.chat.type == "private")


async def _ensure_admin_private(update: Update) -> bool:
    """Ensures only admins in private chat can execute sensitive commands."""
    if not update.message or not update.message.from_user:
        return False

    user_id = update.message.from_user.id
    if not admin_manager.is_admin(user_id):
        await update.message.reply_text("Access denied. Admin only.")
        return False

    if not _is_private_chat(update):
        await update.message.reply_text("For security, use this command in private chat with the bot.")
        return False

    return True


def _parse_qa_payload(payload: str) -> tuple[str, str] | None:
    """Parses '<question> | <answer>' payloads."""
    if "|" not in payload:
        return None

    question, answer = payload.split("|", maxsplit=1)
    question = question.strip()
    answer = answer.strip()

    if not question or not answer:
        return None

    return question, answer


async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return
    await update.message.reply_text(ADMIN_HELP_TEXT)


async def kb_count_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    total = rag.count_knowledge_entries()
    await update.message.reply_text(f"Total knowledge entries: {total}")


async def kb_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    page_size = 20
    offset = 0
    if context.args:
        try:
            page_size = max(1, min(int(context.args[0]), 50))
            if len(context.args) > 1:
                offset = max(0, int(context.args[1]))
        except ValueError:
            await update.message.reply_text("Usage: /kb_list [page_size] [offset]")
            return

    entries = rag.list_knowledge_entries(limit=page_size, offset=offset)
    if not entries:
        await update.message.reply_text("No entries found for this page.")
        return

    lines = [f"Knowledge entries (limit={page_size}, offset={offset}):"]
    for item in entries:
        metadata = item.get("metadata") or {}
        source = metadata.get("source", "unknown")
        preview = (item.get("document") or "").replace("\n", " ").strip()
        preview = preview[:120] + ("..." if len(preview) > 120 else "")
        lines.append(f"- {item['id']} | source={source} | {preview}")

    await update.message.reply_text("\n".join(lines))


async def kb_get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /kb_get <id>")
        return

    doc_id = context.args[0].strip()
    item = rag.get_knowledge_entry(doc_id)
    if not item:
        await update.message.reply_text("Entry not found.")
        return

    metadata = item.get("metadata") or {}
    await update.message.reply_text(
        f"ID: {item['id']}\n"
        f"Source: {metadata.get('source', 'unknown')}\n"
        f"Metadata: {metadata}\n\n"
        f"Content:\n{item.get('document', '')}"
    )


async def kb_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    payload = " ".join(context.args).strip()
    parsed = _parse_qa_payload(payload)
    if not parsed:
        await update.message.reply_text("Usage: /kb_add <question> | <answer>")
        return

    question, answer = parsed
    admin_id = update.message.from_user.id
    doc_id = rag.add_admin_qa_pair(question=question, answer=answer, admin_id=admin_id)

    if not doc_id:
        await update.message.reply_text("Failed to add entry. Check logs and vector store availability.")
        return

    await update.message.reply_text(f"Entry added successfully. ID: {doc_id}")


async def kb_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    payload = " ".join(context.args).strip()
    if "|" not in payload:
        await update.message.reply_text("Usage: /kb_edit <id> | <question> | <answer>")
        return

    first, rest = payload.split("|", maxsplit=1)
    doc_id = first.strip()
    parsed = _parse_qa_payload(rest)
    if not doc_id or not parsed:
        await update.message.reply_text("Usage: /kb_edit <id> | <question> | <answer>")
        return

    question, answer = parsed
    admin_id = update.message.from_user.id
    success = rag.upsert_knowledge_entry(doc_id=doc_id, question=question, answer=answer, admin_id=admin_id)

    if not success:
        await update.message.reply_text("Failed to update entry.")
        return

    await update.message.reply_text(f"Entry updated successfully. ID: {doc_id}")


async def kb_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /kb_delete <id>")
        return

    doc_id = context.args[0].strip()
    success = rag.delete_knowledge_entry(doc_id)
    if not success:
        await update.message.reply_text("Failed to delete entry.")
        return

    await update.message.reply_text(f"Entry deleted successfully. ID: {doc_id}")


async def kb_export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    total = rag.count_knowledge_entries()
    if total == 0:
        await update.message.reply_text("Knowledge base is empty.")
        return

    batch_size = 100
    offset = 0
    lines = [f"Total entries: {total}", ""]

    while offset < total:
        batch = rag.list_knowledge_entries(limit=batch_size, offset=offset)
        if not batch:
            break

        for item in batch:
            metadata = item.get("metadata") or {}
            lines.append(f"ID: {item['id']}")
            lines.append(f"Metadata: {metadata}")
            lines.append("Content:")
            lines.append(item.get("document", ""))
            lines.append("-" * 80)

        offset += batch_size

    export_payload = "\n".join(lines)
    content = export_payload.encode("utf-8")
    file_obj = BytesIO(content)
    file_obj.name = "knowledge_export.txt"
    file_obj.seek(0)

    await update.message.reply_document(document=file_obj, filename="knowledge_export.txt")


def get_payment_escalation_reply(text: str) -> str | None:
    """Returns a fixed support reply for payment visibility questions."""
    lowered = text.lower()

    # Match Uzbek Latin/Cyrillic variants for payment + timing/visibility concerns.
    has_payment = bool(re.search(r"(тулов|тўлов|to'?lov|tolov)", lowered))
    has_time_or_visibility = bool(
        re.search(
            r"(qancha\s*vaqt|канча\s*вакт|қанча\s*вақт|к\S*рина|ko'?rin|көрин)",
            lowered,
        )
    )

    if has_payment and has_time_or_visibility:
        return PAYMENT_ESCALATION_REPLY

    return None


def sanitize_group_answer(answer: str, is_group: bool) -> str:
    """Rewrites DM/private-message instructions in group replies to official escalation wording."""
    if not is_group:
        return answer

    dm_patterns = [
        r"шахсий\s*хабар",
        r"личн(ые|ый)?\s*сообщени(я|е)",
        r"в\s*лс",
        r"dm",
        r"direct\s*message",
        r"private\s*message",
        r"private\s*chat",
        r"personal\s*message",
    ]

    if any(re.search(pattern, answer, flags=re.IGNORECASE) for pattern in dm_patterns):
        return re.sub(
            r"(?i)([\.!?])?\s*$",
            f" {GROUP_SUPPORT_ESCALATION}",
            answer,
            count=1,
        )

    return answer

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

        # Deterministic safeguard for payment delay/escalation wording.
        answer = get_payment_escalation_reply(query)
        if answer is None:
            answer = rag.answer_question(question=query, history=recent_history)

        if answer:
            answer = sanitize_group_answer(answer=answer, is_group=is_group)
        
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
