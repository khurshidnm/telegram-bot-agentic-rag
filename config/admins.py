"""
Admin user management for the Telegram bot.
Admins are support staff who can help clients but shouldn't receive direct bot replies.
However, the bot learns from their interactions with clients.
"""
import os
import logging

logger = logging.getLogger(__name__)


class AdminManager:
    """Manages admin user IDs and their permissions."""
    
    def __init__(self):
        """Initialize admin list from environment variables."""
        admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
        self.admin_ids = set()
        
        if admin_ids_str:
            try:
                self.admin_ids = {
                    int(id.strip()) 
                    for id in admin_ids_str.split(",") 
                    if id.strip().isdigit()
                }
                logger.info(f"Loaded {len(self.admin_ids)} admin user IDs: {self.admin_ids}")
            except ValueError as e:
                logger.error(f"Error parsing ADMIN_USER_IDS: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        return user_id in self.admin_ids
    
    def add_admin(self, user_id: int) -> bool:
        """Add an admin user ID (runtime, not persistent)."""
        if user_id not in self.admin_ids:
            self.admin_ids.add(user_id)
            logger.info(f"Added admin user ID: {user_id}")
            return True
        return False
    
    def remove_admin(self, user_id: int) -> bool:
        """Remove an admin user ID (runtime, not persistent)."""
        if user_id in self.admin_ids:
            self.admin_ids.remove(user_id)
            logger.info(f"Removed admin user ID: {user_id}")
            return True
        return False
    
    def get_all_admins(self) -> set:
        """Get all admin user IDs."""
        return self.admin_ids.copy()


# Global instance
admin_manager = AdminManager()
