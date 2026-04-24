import os
import logging
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import MongoClient

logger = logging.getLogger(__name__)

class MongoMemory:
    def __init__(self):
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
        db_name = os.getenv("DB_NAME", "telegram_bot")
        collection_name = os.getenv("COLLECTION_NAME", "chat_history")
        image_draft_collection_name = os.getenv("IMAGE_DRAFT_COLLECTION_NAME", "image_learning_drafts")
        
        try:
            self.client = MongoClient(mongo_uri)
            self.db = self.client[db_name]
            self.collection = self.db[collection_name]
            self.image_draft_collection = self.db[image_draft_collection_name]
            # Create an index on chat_id and timestamp for faster queries
            self.collection.create_index([("chat_id", 1), ("timestamp", -1)])
            self.image_draft_collection.create_index([("status", 1), ("created_at", -1)])
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

    def create_image_learning_draft(
        self,
        chat_id: int,
        question: str,
        answer: str,
        created_by_user_id: int,
        created_by_username: str,
        source_type: str,
    ) -> str | None:
        """Stores an image-derived learning draft for super-admin review."""
        doc = {
            "chat_id": chat_id,
            "question": question,
            "answer": answer,
            "created_by_user_id": created_by_user_id,
            "created_by_username": created_by_username,
            "source_type": source_type,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "reviewed_at": None,
            "reviewed_by_user_id": None,
            "reviewed_by_username": None,
            "kb_entry_id": None,
        }

        try:
            result = self.image_draft_collection.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to create image learning draft: {e}")
            return None

    def list_image_learning_drafts(self, status: str = "pending", limit: int = 20, offset: int = 0) -> list[dict]:
        """Lists image-learning drafts with pagination."""
        try:
            cursor = (
                self.image_draft_collection.find({"status": status})
                .sort("created_at", -1)
                .skip(offset)
                .limit(limit)
            )
            drafts = []
            for doc in cursor:
                doc["id"] = str(doc.pop("_id"))
                drafts.append(doc)
            return drafts
        except Exception as e:
            logger.error(f"Failed to list image learning drafts: {e}")
            return []

    def get_image_learning_draft(self, draft_id: str) -> dict | None:
        """Fetches one image-learning draft by id."""
        try:
            doc = self.image_draft_collection.find_one({"_id": ObjectId(draft_id)})
            if not doc:
                return None
            doc["id"] = str(doc.pop("_id"))
            return doc
        except Exception as e:
            logger.error(f"Failed to get image learning draft {draft_id}: {e}")
            return None

    def set_image_learning_draft_status(
        self,
        draft_id: str,
        status: str,
        reviewed_by_user_id: int,
        reviewed_by_username: str,
        kb_entry_id: str | None = None,
    ) -> bool:
        """Approves or rejects an image-learning draft."""
        try:
            result = self.image_draft_collection.update_one(
                {"_id": ObjectId(draft_id)},
                {
                    "$set": {
                        "status": status,
                        "reviewed_at": datetime.utcnow(),
                        "reviewed_by_user_id": reviewed_by_user_id,
                        "reviewed_by_username": reviewed_by_username,
                        "kb_entry_id": kb_entry_id,
                    }
                },
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update image learning draft {draft_id}: {e}")
            return False
