# Admin Management Guide

This document explains role-based admin management for support operations in Telegram groups.

## How Admins Work

The bot uses two admin roles:

✅ **Super Admin can:**
- Run private governance commands (`/kb_*`, `/image_*`, `/admin_help`)
- Approve or reject image-learning drafts

✅ **Trainer Admin can:**
- Help clients directly in groups
- Train the bot from reply-based interactions

❌ **Trainer admins don't get:**
- Bot replies in group workflows (to avoid bot/staff collisions)

📚 **What the bot learns:**
- When a trainer admin replies to a client question, the bot **learns from that interaction**
- This builds the bot's knowledge base over time
- Admin responses train the RAG pipeline to answer similar questions better

## Configuration

### Setting Role User IDs

Add role IDs to the `.env` file in your project root:

```env
SUPER_ADMIN_USER_IDS=123456789
TRAINER_ADMIN_USER_IDS=987654321,111222333,444555666
```

**To find an admin's User ID:**

1. Have them open a private chat with the bot
2. The bot logs their user ID in the console/logs
3. Or use `@userinfobot` in Telegram to get their ID

**Important:** Separate user IDs with **commas** and **no spaces** before/after commas.

Backward compatibility:
- If `TRAINER_ADMIN_USER_IDS` is missing, the bot falls back to `ADMIN_USER_IDS` for trainer access.
- Prefer using explicit role variables in all new setups.

### Environment Variable Location

The `.env` file should be in your project root directory:
```
/your-project-root/.env
```

Example:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefg
MONGO_URI=mongodb://localhost:27017/
DB_NAME=telegram_bot
COLLECTION_NAME=chat_history
STRICTNESS_LEVEL=BALANCED
SUPER_ADMIN_USER_IDS=123456789
TRAINER_ADMIN_USER_IDS=987654321,111222333
```

## How the Bot Handles Messages

### From Regular Clients
```
Client: "How do I create an invoice?"
Bot: "To create an invoice, follow these steps..."
```

### From Trainer Admins Responding to Clients
```
Client: "How do I create an invoice?"
Admin: "Here are the steps to create an invoice..."
[Bot learns this Q&A pair silently - no reply from bot]
```

### From Trainer Admins Asking Directly in Group
```
Trainer Admin: "How do I create an invoice?"
[Bot stays silent - no response to admins]
```

### From Super Admins in Private Chat
```
Super Admin: /kb_add Question | Answer
Bot: "✅ Added knowledge entry..."
```

## Monitoring Admin Interactions

The bot logs all messages including role-based interactions:

```
INFO - Trainer admin john_doe sent group message, skipping bot response
INFO - Trainer admin john_doe replied to client. Learning Q&A pair...
```

Check logs with:
```bash
# On the server running the bot
journalctl -u telegram-bot.service -f  # Real-time logs
journalctl -u telegram-bot.service | tail -100  # Last 100 lines
```

## Adding/Removing Admins

### Method 1: Update `.env` (Recommended)
1. Edit your `.env` file
2. Update `SUPER_ADMIN_USER_IDS` and/or `TRAINER_ADMIN_USER_IDS`
3. Restart the bot:
   ```bash
   sudo systemctl restart telegram-bot.service
   ```

### Method 2: Runtime Management (Temporary)
If you need to add/remove admins temporarily without restarting, you can modify the code to support `/admin_add` and `/admin_remove` commands:

Example implementation:
```python
async def admin_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to add a new admin (requires authentication)."""
    if update.message.from_user.id not in admin_manager.admin_ids:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    try:
        user_id = int(context.args[0])
        if admin_manager.add_admin(user_id):
            await update.message.reply_text(f"Added admin: {user_id}")
        else:
            await update.message.reply_text(f"User {user_id} is already an admin.")
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /admin_add <user_id>")
```

## Best Practices

1. **Keep admin list updated** - Whenever team members join or leave, update the list immediately
2. **Test after adding** - Have a new admin send a message to verify they don't get bot replies
3. **Monitor learning** - Check logs to confirm the bot is learning from admin-client interactions
4. **Backup .env** - Keep a secure backup of your admin list in case of server issues

## Troubleshooting

### Trainer admin is still getting bot responses
- Verify the user ID in `TRAINER_ADMIN_USER_IDS` is correct
- Check there are no spaces around commas
- Restart the bot: `sudo systemctl restart telegram-bot.service`
- Check logs: `journalctl -u telegram-bot.service -f`

### Bot is not learning from admin replies
- Confirm the admin is replying to a client's message (using reply feature)
- Check the bot logs for "Learning Q&A pair" messages
- Verify the admin's response and client's question both have text

### New role assignment doesn't have effect
- Restart the bot service after updating `.env`
- Confirm the changes were saved to `.env`

## Admin Learning Flow

```
Client: "Question?"
     ↓
Trainer Admin: (replies to client's message)
     ↓
Bot logs the question and answer
     ↓
RAG Pipeline learns the Q&A pair
     ↓
Bot database is updated for future similar questions
```

This workflow ensures:
- Admins maintain real human support
- Bot learns from successful admin-client interactions  
- Bot doesn't interrupt admin-client conversations
- Knowledge base grows organically from support interactions
