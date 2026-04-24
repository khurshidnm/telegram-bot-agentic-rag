# VPS Deployment Guide (Hostinger / Ubuntu)

To keep your bot running 24/7 on your Hostinger VPS, you need to clone the code to your server, set up the database, and run the bot as a background service using `systemd`.

Follow these step-by-step instructions. These commands assume your VPS is running **Ubuntu** or **Debian**.

## Step 1: Connect to your VPS
Open your terminal and SSH into your Hostinger VPS using the IP address provided in your Hostinger dashboard.
```bash
ssh root@YOUR_VPS_IP_ADDRESS
```

## Step 2: Install System Requirements
Update your server and install Python, Git, and MongoDB.
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-venv python3-pip git -y

# Install MongoDB (Ubuntu 22.04/24.04 standard repository)
sudo apt install mongodb -y

# Start MongoDB and enable it to run on server boot
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

## Step 3: Clone the Repository
Download your bot's code from GitHub to your server.
```bash
git clone https://github.com/khurshidnm/telegram-bot-agentic-rag.git
cd telegram-bot-agentic-rag
```

## Step 4: Set Up the Python Environment
```bash
# Create the virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install all the packages
pip install -r requirements.txt
```

## Step 5: Configure the `.env` file
You need to recreate your `.env` file on the server.
```bash
nano .env
```
Paste your API keys and configuration into the editor:
```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
MONGO_URI=mongodb://localhost:27017/
DB_NAME=telegram_bot
COLLECTION_NAME=chat_history
IMAGE_DRAFT_COLLECTION_NAME=image_learning_drafts
STRICTNESS_LEVEL=BALANCED
SUPER_ADMIN_USER_IDS=123456789
TRAINER_ADMIN_USER_IDS=987654321,112233445
```

**Role IDs:**
- `SUPER_ADMIN_USER_IDS`: users with private admin command access (`/kb_*`, `/image_*`, `/admin_help`).
- `TRAINER_ADMIN_USER_IDS`: support staff IDs for group training interactions.

See [ADMIN_MANAGEMENT.md](ADMIN_MANAGEMENT.md) for details.

Press `CTRL + O`, `Enter` to save, and `CTRL + X` to exit.

## Step 6: Transfer and Ingest Your Document
Since your local `chroma_db` database is ignored in Git (because vector databases shouldn't be pushed to GitHub), you need to ingest your document on the server.
1. Make sure your `data.docx` is inside the `docs/` folder on the server. 
2. Run the ingestion script:
```bash
python3 ingest.py
```

## Step 7: Set up 24/7 Background Service (`systemd`)
To ensure the bot stays alive even if you close the terminal or the server restarts, we use `systemd`.

1. Copy the provided service file to the systemd directory:
```bash
sudo cp telegram-bot.service /etc/systemd/system/
```
*(Note: If you didn't clone the project into `/root/telegram-bot-agentic-rag`, you must edit the `WorkingDirectory` and `ExecStart` paths inside `telegram-bot.service` before copying it!)*

2. Reload systemd to recognize the new file:
```bash
sudo systemctl daemon-reload
```

3. Start the bot:
```bash
sudo systemctl start telegram-bot
```

4. Enable the bot to start automatically if the VPS ever reboots:
```bash
sudo systemctl enable telegram-bot
```

## Step 8: Check the Bot's Status
To see if the bot is running properly and check its live logs:
```bash
sudo systemctl status telegram-bot
```
To watch the live logs as they come in:
```bash
journalctl -u telegram-bot -f
```
