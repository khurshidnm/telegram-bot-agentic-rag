import os
import logging
import re
import base64
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

PAYMENT_ESCALATION_REPLY_LATIN = (
    "Assalomu alaykum! To'lovingiz odatda bir necha daqiqa ichida ko'rinadi. "
    "Agar biron-bir muammo yuzaga kelsa yoki to'lov ko'rinmasa, iltimos, "
    "@keepingmanager Telegram manziliga to'lov chekini yuboring, tekshirib beramiz."
)

GROUP_SUPPORT_ESCALATION_CYRILLIC = (
    "Илтимос, @keepingmanager Telegram манзилига юборинг."
)

GROUP_SUPPORT_ESCALATION_LATIN = (
    "Iltimos, @keepingmanager Telegram manziliga yuboring."
)

GRATITUDE_REPLY = (
    "Sizga yordam bera olganimdan xursandman! Agar yana savollaringiz bo'lsa, bemalol "
    "so'rashingiz mumkin. Agar mutaxassislarimiz bilan bog'lanmoqchi bo'lsangiz ushbu "
    "@keepingmanager Telegram manziliga yozing."
)

ADMIN_HELP_TEXT = (
    "Super Admin Knowledge Commands:\n"
    "/kb_count - Show total knowledge entries\n"
    "/kb_list [page_size] [offset] - List entries with IDs\n"
    "/kb_get <id> - Show one entry\n"
    "/kb_add <question> | <answer> - Add Q&A pair\n"
    "/kb_edit <id> | <question> | <answer> - Update entry\n"
    "/kb_delete <id> - Delete entry\n"
    "/kb_export - Export all entries as a text file\n"
    "/learning_drafts [limit] [offset] - List pending learning drafts\n"
    "/learning_approve <draft_id> - Approve draft and add to KB\n"
    "/learning_reject <draft_id> - Reject draft\n"
    "(Legacy aliases: /image_drafts, /image_approve, /image_reject)\n"
    "\n"
    "Bot Control Commands:\n"
    "/bot_on - Enable bot answers (keep learning active)\n"
    "/bot_off - Disable bot answers (keep learning active)\n"
    "/bot_status - Show current bot status\n"
    "\n"
    "/admin_help - Show this help"
)


def _is_private_chat(update: Update) -> bool:
    return bool(update.message and update.message.chat.type == "private")


async def _ensure_admin_private(update: Update) -> bool:
    """Ensures only super admins in private chat can execute sensitive commands."""
    if not update.message or not update.message.from_user:
        return False

    user_id = update.message.from_user.id
    if not admin_manager.is_super_admin(user_id):
        await update.message.reply_text("Access denied. Super admin only.")
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


async def bot_on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enables the bot to answer questions (super-admin only)."""
    if not await _ensure_admin_private(update):
        return
    
    try:
        memory.set_bot_enabled(True)
        logger.info("Bot enabled by super-admin %s", update.message.from_user.username)
        await update.message.reply_text(
            "✅ Bot is now **ENABLED**\n\n"
            "The bot will answer questions in the group.\n"
            "Learning remains active regardless of this setting."
        )
    except Exception as e:
        logger.error(f"Failed to enable bot: {e}")
        await update.message.reply_text("❌ Failed to enable bot. Check logs.")


async def bot_off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Disables the bot from answering (but keeps learning active)."""
    if not await _ensure_admin_private(update):
        return
    
    try:
        memory.set_bot_enabled(False)
        logger.info("Bot disabled by super-admin %s", update.message.from_user.username)
        await update.message.reply_text(
            "⛔ Bot is now **DISABLED**\n\n"
            "The bot will NOT answer questions in the group.\n"
            "However, learning from trainer responses will continue."
        )
    except Exception as e:
        logger.error(f"Failed to disable bot: {e}")
        await update.message.reply_text("❌ Failed to disable bot. Check logs.")


async def bot_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the current bot status (super-admin only)."""
    if not await _ensure_admin_private(update):
        return
    
    try:
        is_enabled = memory.is_bot_enabled()
        status = "✅ ENABLED" if is_enabled else "⛔ DISABLED"
        await update.message.reply_text(
            f"**Bot Status**: {status}\n\n"
            f"• Answering questions: {'Yes' if is_enabled else 'No'}\n"
            f"• Learning from trainers: Always active"
        )
    except Exception as e:
        logger.error(f"Failed to check bot status: {e}")
        await update.message.reply_text("❌ Failed to check bot status. Check logs.")


async def my_role_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Returns current caller role and user ID for quick diagnostics."""
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    roles: list[str] = []

    if admin_manager.is_super_admin(user_id):
        roles.append("Super Admin")
    if admin_manager.is_trainer_admin(user_id):
        roles.append("Trainer Admin")
    if not roles:
        roles.append("Regular User")

    await update.message.reply_text(
        f"Your user ID: {user_id}\n"
        f"Your role: {', '.join(roles)}"
    )


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


def _draft_question_from_message(message) -> str | None:
    """Builds a learnable draft question from a replied user message."""
    if not message:
        return None

    question = (message.text or message.caption or "").strip()
    if question:
        return question

    if _message_has_image(message):
        return "[Image-only user question without caption]"

    return None


async def _notify_super_admins_about_draft(
    context: ContextTypes.DEFAULT_TYPE,
    draft_id: str,
    question: str,
    answer: str,
    source_type: str,
    trainer_username: str,
) -> None:
    """Sends a pending learning draft notification to all configured super admins."""
    if not admin_manager.super_admin_ids:
        logger.warning("No super admins configured. Draft %s is pending but nobody was notified.", draft_id)
        return

    question_preview = (question or "").replace("\n", " ").strip()
    answer_preview = (answer or "").replace("\n", " ").strip()
    question_preview = question_preview[:220] + ("..." if len(question_preview) > 220 else "")
    answer_preview = answer_preview[:220] + ("..." if len(answer_preview) > 220 else "")

    notification_text = (
        "New learning draft pending approval.\n"
        f"Draft ID: {draft_id}\n"
        f"Created by: {trainer_username}\n"
        f"Source: {source_type}\n"
        f"Question: {question_preview}\n"
        f"Answer: {answer_preview}\n\n"
        "Review commands:\n"
        f"/learning_approve {draft_id}\n"
        f"/learning_reject {draft_id}"
    )

    for super_admin_id in admin_manager.super_admin_ids:
        try:
            await context.bot.send_message(chat_id=super_admin_id, text=notification_text)
        except Exception as e:
            logger.error(
                "Failed to notify super admin %s about draft %s: %s",
                super_admin_id,
                draft_id,
                e,
            )


async def image_drafts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    limit = 20
    offset = 0
    if context.args:
        try:
            limit = max(1, min(int(context.args[0]), 50))
            if len(context.args) > 1:
                offset = max(0, int(context.args[1]))
        except ValueError:
            await update.message.reply_text("Usage: /learning_drafts [limit] [offset]")
            return

    drafts = memory.list_image_learning_drafts(status="pending", limit=limit, offset=offset)
    if not drafts:
        await update.message.reply_text("No pending learning drafts.")
        return

    lines = [f"Pending learning drafts (limit={limit}, offset={offset}):"]
    for draft in drafts:
        question_preview = (draft.get("question") or "").replace("\n", " ").strip()
        question_preview = question_preview[:80] + ("..." if len(question_preview) > 80 else "")
        lines.append(
            f"- {draft['id']} | by={draft.get('created_by_username', 'unknown')} | "
            f"source={draft.get('source_type', 'unknown')} | q={question_preview}"
        )

    await update.message.reply_text("\n".join(lines))


async def image_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /learning_approve <draft_id>")
        return

    draft_id = context.args[0].strip()
    draft = memory.get_image_learning_draft(draft_id)
    if not draft:
        await update.message.reply_text("Draft not found.")
        return

    if draft.get("status") != "pending":
        await update.message.reply_text(f"Draft already reviewed. Status: {draft.get('status')}")
        return

    question = (draft.get("question") or "").strip()
    answer = (draft.get("answer") or "").strip()
    if not question or not answer:
        await update.message.reply_text("Draft has empty question or answer. Reject and recreate it.")
        return

    reviewer_id = update.message.from_user.id
    reviewer_username = update.message.from_user.username or update.message.from_user.first_name

    kb_entry_id = rag.add_admin_qa_pair(question=question, answer=answer, admin_id=reviewer_id)
    if not kb_entry_id:
        await update.message.reply_text("Failed to add approved draft to KB.")
        return

    ok = memory.set_image_learning_draft_status(
        draft_id=draft_id,
        status="approved",
        reviewed_by_user_id=reviewer_id,
        reviewed_by_username=reviewer_username,
        kb_entry_id=kb_entry_id,
    )
    if not ok:
        await update.message.reply_text("KB was updated, but draft status update failed. Check logs.")
        return

    await update.message.reply_text(f"Draft approved and added to production KB. Draft ID: {draft_id} | KB ID: {kb_entry_id}")


async def image_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _ensure_admin_private(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /learning_reject <draft_id>")
        return

    draft_id = context.args[0].strip()
    draft = memory.get_image_learning_draft(draft_id)
    if not draft:
        await update.message.reply_text("Draft not found.")
        return

    if draft.get("status") != "pending":
        await update.message.reply_text(f"Draft already reviewed. Status: {draft.get('status')}")
        return

    reviewer_id = update.message.from_user.id
    reviewer_username = update.message.from_user.username or update.message.from_user.first_name
    ok = memory.set_image_learning_draft_status(
        draft_id=draft_id,
        status="rejected",
        reviewed_by_user_id=reviewer_id,
        reviewed_by_username=reviewer_username,
    )

    if not ok:
        await update.message.reply_text("Failed to reject draft.")
        return

    await update.message.reply_text(f"Draft rejected successfully. Draft ID: {draft_id}")


# Generic command names for all learning drafts (image + text), keeping legacy image_* aliases.
async def learning_drafts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await image_drafts_command(update, context)


async def learning_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await image_approve_command(update, context)


async def learning_reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await image_reject_command(update, context)


def get_payment_escalation_reply(text: str) -> str | None:
    """Returns a fixed support reply for payment visibility questions."""
    lowered = text.lower()
    script = _detect_text_script(text)

    # Match Uzbek Latin/Cyrillic variants for payment + timing/visibility concerns.
    has_payment = bool(re.search(r"(тулов|тўлов|to'?lov|tolov)", lowered))
    has_time_or_visibility = bool(
        re.search(
            r"(qancha\s*vaqt|канча\s*вакт|қанча\s*вақт|к\S*рина|ko'?rin|көрин)",
            lowered,
        )
    )

    if has_payment and has_time_or_visibility:
        return PAYMENT_ESCALATION_REPLY_LATIN if script == "Latin" else PAYMENT_ESCALATION_REPLY

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
        script = _detect_text_script(answer)
        escalation = (
            GROUP_SUPPORT_ESCALATION_LATIN if script == "Latin" else GROUP_SUPPORT_ESCALATION_CYRILLIC
        )
        return re.sub(
            r"(?i)([\.!?])?\s*$",
            f" {escalation}",
            answer,
            count=1,
        )

    return answer


def _message_has_image(message) -> bool:
    """Returns true when a Telegram message includes an image payload."""
    if not message:
        return False

    if message.photo:
        return True

    if message.document and (message.document.mime_type or "").startswith("image/"):
        return True

    return False


def _detect_text_script(text: str) -> str:
    """Detects whether text is primarily Latin or Cyrillic."""
    if not text:
        return "Latin"

    cyrillic_count = len(re.findall(r"[А-Яа-яЁёЎўҚқҒғҲҳЪъЬь]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))

    if cyrillic_count > latin_count:
        return "Cyrillic"
    return "Latin"


def _is_gratitude_message(text: str) -> bool:
    """Detects short thank-you messages in Latin or Cyrillic variants."""
    if not text:
        return False

    lowered = text.lower().strip()
    gratitude_patterns = [
        r"\bthank\s*you\b",
        r"\bthanks\b",
        r"\btahnk\s*you\b",
        r"\brahmat\b",
        r"\braxmat\b",
        r"\bрахмат\b",
    ]

    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in gratitude_patterns)


def _sanitize_language_restriction_reply(answer: str) -> str:
    """Prevents sending exclusionary language-restriction wording to users."""
    if not answer:
        return answer

    lowered = answer.lower()
    restricted_patterns = [
        r"только\s+на\s+узбекском\s+или\s+русском",
        r"могу\s+ответить\s+вам\s+только",
        r"faqat\s+o'?zbek\s+yoki\s+rus\s+tilida",
        r"faqat\s+uzbek\s+va\s+rus\s+tilida",
    ]

    if any(re.search(pattern, lowered) for pattern in restricted_patterns):
        if re.search(r"[а-яА-Я]", answer):
            return "Пожалуйста, уточните ваш вопрос, и я постараюсь помочь максимально точно."
        return "Iltimos, savolingizni aniqroq yozing, men sizga yordam berishga harakat qilaman."

    return answer


def _normalize_brand_text(text: str) -> str:
    """Normalizes common speech/transcription brand variants to Keeping."""
    if not text:
        return text

    # Normalize likely misrecognitions/transliterations of the product name.
    return re.sub(r"(?i)\bkipling\b|\bкиплинг\b|\bкиплинг\b", "Keeping", text)


def _sanitize_brand_name(answer: str) -> str:
    """Ensures outgoing answers always use the canonical product name Keeping."""
    if not answer:
        return answer
    return _normalize_brand_text(answer)


async def _download_image_bytes(message, context: ContextTypes.DEFAULT_TYPE) -> tuple[bytes, str] | tuple[None, None]:
    """Downloads image bytes and returns (bytes, mime_type)."""
    file_id = None
    mime_type = "image/jpeg"

    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
        mime_type = message.document.mime_type or mime_type

    if not file_id:
        return None, None

    telegram_file = await context.bot.get_file(file_id)
    image_buffer = BytesIO()
    await telegram_file.download_to_memory(out=image_buffer)
    image_buffer.seek(0)
    return image_buffer.read(), mime_type


async def _extract_image_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Extracts structured context from image using OpenAI multimodal model."""
    if not update.message or not _message_has_image(update.message):
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY is not configured. Cannot analyze image message.")
        return None

    try:
        from openai import AsyncOpenAI

        image_bytes, mime_type = await _download_image_bytes(update.message, context)
        if not image_bytes:
            return None

        encoded = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{encoded}"

        image_model = os.getenv("IMAGE_ANALYSIS_MODEL", "gpt-4o-mini")
        user_caption = (update.message.caption or "").strip()
        analysis_instruction = (
            "Extract support-relevant context from this image. "
            "Return only concise factual details: visible text, numbers, error messages, form fields, "
            "and what user is likely asking. "
            "If caption language is Uzbek or Russian, keep output in that same language. "
            "If no useful details are visible, return exactly: NO_IMAGE_CONTEXT"
        )

        client = AsyncOpenAI(api_key=api_key)
        completion = await client.chat.completions.create(
            model=image_model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": "You analyze support screenshots accurately and concisely.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Caption: {user_caption or 'None'}\n\n{analysis_instruction}",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        },
                    ],
                },
            ],
        )

        content = (completion.choices[0].message.content or "").strip() if completion.choices else ""
        if not content or content == "NO_IMAGE_CONTEXT":
            return None
        return content
    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        return None


async def _answer_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
    chat_id: int,
    is_group: bool,
):
    """Runs standard answer generation and persistence flow for a query."""
    try:
        query = _normalize_brand_text(query)
        script_hint = _detect_text_script(query)

        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        recent_history = memory.get_recent_history(chat_id=chat_id, minutes=5)

        answer = get_payment_escalation_reply(query)
        if answer is None:
            answer = rag.answer_question(
                question=query,
                history=recent_history,
                script_hint=script_hint,
            )

        if answer:
            answer = _sanitize_language_restriction_reply(answer=answer)
            answer = _sanitize_brand_name(answer)
            answer = sanitize_group_answer(answer=answer, is_group=is_group)

        if answer is None:
            logger.info("Bot is not confident in the answer. Staying silent.")
            return

        await update.message.reply_text(answer)

        memory.add_message(
            chat_id=chat_id,
            user_id=context.bot.id,
            username=context.bot.username or "Assistant",
            message=answer,
            is_bot=True,
        )
    except Exception as e:
        logger.error(f"Error answering query: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming text messages."""
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name
    text = update.message.text
    is_group = update.message.chat.type in ['group', 'supergroup']
    is_trainer_admin = admin_manager.is_trainer_admin(user_id)

    # 1. Log the incoming message to MongoDB (admins included)
    memory.add_message(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        message=text,
        is_bot=False
    )

    # 2. Handle trainer admin messages in groups: learn from interactions but don't reply.
    if is_trainer_admin and is_group:
        if update.message.reply_to_message:
            replied_msg = update.message.reply_to_message
            replied_user_id = replied_msg.from_user.id
            
            # Learn only from trainer admin replies to non-admin, non-bot users.
            if not admin_manager.is_admin(replied_user_id) and replied_user_id != context.bot.id:
                if _message_has_image(replied_msg):
                    question = _draft_question_from_message(replied_msg)
                    answer = text.strip()
                    if question and answer:
                        draft_id = memory.create_image_learning_draft(
                            chat_id=chat_id,
                            question=question,
                            answer=answer,
                            created_by_user_id=user_id,
                            created_by_username=username,
                            source_type="text_reply_on_image",
                        )
                        logger.info(
                            "Created image-learning draft from trainer text reply. draft_id=%s",
                            draft_id,
                        )
                        if draft_id:
                            await _notify_super_admins_about_draft(
                                context=context,
                                draft_id=draft_id,
                                question=question,
                                answer=answer,
                                source_type="text_reply_on_image",
                                trainer_username=username,
                            )
                    return

                question = _draft_question_from_message(replied_msg)
                answer = text.strip()
                if question and answer:
                    draft_id = memory.create_image_learning_draft(
                        chat_id=chat_id,
                        question=question,
                        answer=answer,
                        created_by_user_id=user_id,
                        created_by_username=username,
                        source_type="text_reply",
                    )
                    logger.info(
                        "Created learning draft from trainer text reply. draft_id=%s",
                        draft_id,
                    )
                    if draft_id:
                        await _notify_super_admins_about_draft(
                            context=context,
                            draft_id=draft_id,
                            question=question,
                            answer=answer,
                            source_type="text_reply",
                            trainer_username=username,
                        )
        
        # Don't respond to trainer admins in groups; they are support staff.
        logger.info(f"Trainer admin {username} sent group message, skipping bot response")
        return

    # 4. Determine if the bot should process this message.
    bot_username = context.bot.username
    
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

    # Check if bot is enabled; if not, don't respond (but learning continues elsewhere)
    if not memory.is_bot_enabled():
        logger.info("Bot is disabled; skipping response to user %s", username)
        return

    # Clean the bot's tag from the message for the query
    query = text.replace(f"@{bot_username}", "").strip() if bot_username else text

    if _is_gratitude_message(query):
        await update.message.reply_text(GRATITUDE_REPLY)
        memory.add_message(
            chat_id=chat_id,
            user_id=context.bot.id,
            username=context.bot.username or "Assistant",
            message=GRATITUDE_REPLY,
            is_bot=True,
        )
        return

    await _answer_query(
        update=update,
        context=context,
        query=query,
        chat_id=chat_id,
        is_group=is_group,
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming voice messages with a text-only guidance reply."""
    if not update.message or not update.message.voice:
        return

    await update.message.reply_text(
        "Hozircha men faqat yozma savollarga yordam bera olaman. "
        "Iltimos, savolingizni qisqacha yozib yuboring."
    )


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming image messages by extracting image context and answering with RAG."""
    if not update.message or not _message_has_image(update.message):
        return

    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    username = update.message.from_user.username or update.message.from_user.first_name
    is_group = update.message.chat.type in ["group", "supergroup"]
    is_trainer_admin = admin_manager.is_trainer_admin(user_id)

    image_context = await _extract_image_context(update, context)
    caption = (update.message.caption or "").strip()

    if is_trainer_admin and is_group:
        # Never auto-learn from image-based interactions to avoid generalized confusion.
        logger.info(f"Trainer admin {username} sent image in group, skipping auto-learn and reply")
        return

    bot_username = context.bot.username
    should_respond = False

    if is_group:
        if bot_username and f"@{bot_username}" in caption:
            should_respond = True
        elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
            should_respond = True
        elif "?" in caption:
            should_respond = True
    else:
        should_respond = True

    if not should_respond:
        return

    # Check if bot is enabled; if not, don't respond (but learning continues elsewhere)
    if not memory.is_bot_enabled():
        logger.info("Bot is disabled; skipping response to user %s", username)
        return

    query_parts = []
    if caption:
        query_parts.append(caption)
    if image_context:
        query_parts.append(f"Image context: {image_context}")

    if not query_parts:
        if not is_group:
            await update.message.reply_text(
                "Rasmni oldim, lekin savolni aniqlay olmadim. Iltimos, rasm bilan birga qisqa savol yozing."
            )
        return

    query = "\n\n".join(query_parts)

    memory.add_message(
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        message=f"[image query] {query}",
        is_bot=False,
    )

    await _answer_query(
        update=update,
        context=context,
        query=query,
        chat_id=chat_id,
        is_group=is_group,
    )

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
