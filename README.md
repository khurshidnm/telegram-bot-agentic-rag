# Agentic RAG Telegram Bot

A highly intelligent, context-aware Telegram Assistant. 

This bot is designed to serve as a hyper-confident, autonomous agent for Telegram groups and private chats. It utilizes Retrieval-Augmented Generation (RAG) to answer questions based on a localized knowledge base, and features a unique **Continuous Human Learning** mechanism.

## ✨ Features

- **Confidence-Based Responses**: The bot evaluates incoming questions against its knowledge base (Word, Excel, PDF, TXT, MD). It only responds if it is highly confident in the answer. If it doesn't know, it remains completely silent.
- **Continuous Human Learning**: When the bot stays silent, human assistants can step in and reply to the user. The bot quietly observes these interactions and permanently learns the Q&A pairs. The next time the question is asked, the bot will answer it immediately!
- **Multi-Format Ingestion**: Supports `.docx`, `.xlsx`, `.pdf`, `.txt`, and `.md` files seamlessly.
- **Persistent Memory**: Integrates with MongoDB to maintain conversation history, allowing the bot to understand context over time.
- **Vector Database**: Uses ChromaDB locally to store and quickly retrieve semantic embeddings via OpenAI.

## 🚀 Tech Stack

- **Python 3.11+**
- **python-telegram-bot** for asynchronous Telegram interactions.
- **LangChain & OpenAI** for the RAG pipeline and LLM orchestration.
- **ChromaDB** for local vector storage.
- **MongoDB** for chat history and logging.

## ⚙️ Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/agentic-telegram-bot.git
cd agentic-telegram-bot
```

### 2. Create a Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables
Create a `.env` file in the root directory (you can copy `.env.example`):
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
MONGO_URI=mongodb://localhost:27017/
DB_NAME=telegram_bot
COLLECTION_NAME=chat_history

# Comma-separated list of Telegram User IDs for Human Assistants
ADMIN_USER_IDS=123456789
```

### 5. Start MongoDB
Make sure you have MongoDB installed and running locally:
```bash
brew services start mongodb-community@7.0
```

### 6. Ingest Knowledge Base
Place your documents (e.g., `data.docx`, PDFs) inside the `docs/` folder, then run:
```bash
python3 ingest.py
```

### 7. Run the Bot
```bash
python3 bot.py
```

## 🧠 How the Learning Works
1. A user asks: *"What is the annual price?"*
2. The bot checks its database. If it doesn't know, it stays silent.
3. An admin (whose Telegram ID is in `ASSISTANT_USER_IDS`) replies to the user: *"The price is $100."*
4. The bot automatically learns this pair and saves it to its Vector DB.
5. A new user asks: *"How much does it cost?"* -> The bot answers immediately!

## 🔐 Admin Knowledge Management

The bot supports secure, admin-only knowledge operations in private chat.

- `/admin_help` - Shows admin command help
- `/kb_count` - Shows total entries in vector knowledge
- `/kb_list [page_size] [offset]` - Lists entries with IDs and previews
- `/kb_get <id>` - Displays full entry by ID
- `/kb_add <question> | <answer>` - Adds a new Q&A entry
- `/kb_edit <id> | <question> | <answer>` - Updates an existing entry
- `/kb_delete <id>` - Deletes an entry by ID
- `/kb_export` - Exports all knowledge entries as a text file

Security behavior:
- Only Telegram users listed in `ADMIN_USER_IDS` can run these commands.
- Admin commands are accepted only in private chat with the bot.

## 👨‍💻 Author
**Khurshid Normurodov**
