import os
import logging
from datetime import datetime, timedelta
from pymongo import MongoClient

logger = logging.getLogger(__name__)

class MongoMemory:
    def __init__(self):
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        db_name = os.getenv("DB_NAME", "telegram_bot")
        collection_name = os.getenv("COLLECTION_NAME", "chat_history")
        
        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            # Create an index on chat_id and timestamp for faster queries
            self.collection.create_index([("chat_id", 1), ("timestamp", -1)])
            logger.info("Connected to MongoDB successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            # Raise or handle as needed for production. Here we'll just log it.
            # In a robust setup, you might want it to crash if DB isn't available.

    def add_message(self, chat_id: int, user_id: int, username: str, message: str, is_bot: bool = False):
        """Stores a message in the database."""
        doc = {
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "message": message,
            "is_bot": is_bot,
            "timestamp": datetime.utcnow()
        }
        try:
            self.collection.insert_one(doc)
        except Exception as e:
            logger.error(f"Failed to insert message into MongoDB: {e}")

    def get_recent_history(self, chat_id: int, minutes: int = 5) -> str:
        """Retrieves chat history for the last `minutes`."""
        time_threshold = datetime.utcnow() - timedelta(minutes=minutes)
        try:
            cursor = self.collection.find(
                {
                    "chat_id": chat_id,
                    "timestamp": {"$gte": time_threshold}
                }
            ).sort("timestamp", 1)  # Sort chronologically

            history = []
            for doc in cursor:
                sender = "Assistant" if doc.get("is_bot") else doc.get("username", "Unknown User")
                history.append(f"{sender}: {doc.get('message')}")

            return "\n".join(history)
        except Exception as e:
            logger.error(f"Failed to retrieve history from MongoDB: {e}")
            return ""
