"""
Role management for the Telegram bot.
- Super admins can manage KB content via bot commands.
- Trainer admins can train the bot from group interactions.
"""
import os
import logging

logger = logging.getLogger(__name__)


class AdminManager:
    """Manages role-based user IDs and permissions."""

    def __init__(self):
        """Initialize role lists from environment variables."""
        # Backward compatibility: if TRAINER_ADMIN_USER_IDS is not set,
        # ADMIN_USER_IDS is treated as trainer admin IDs.
        super_admin_ids_str = os.getenv("SUPER_ADMIN_USER_IDS", "")
        trainer_admin_ids_str = os.getenv("TRAINER_ADMIN_USER_IDS", "") or os.getenv("ADMIN_USER_IDS", "")

        self.super_admin_ids = self._parse_ids(super_admin_ids_str, "SUPER_ADMIN_USER_IDS")
        self.trainer_admin_ids = self._parse_ids(trainer_admin_ids_str, "TRAINER_ADMIN_USER_IDS/ADMIN_USER_IDS")

        logger.info(
            "Loaded roles: super_admins=%s trainer_admins=%s",
            self.super_admin_ids,
            self.trainer_admin_ids,
        )

    @staticmethod
    def _parse_ids(raw_value: str, env_name: str) -> set[int]:
        ids: set[int] = set()
        if not raw_value:
            return ids

        try:
            ids = {
                int(user_id.strip())
                for user_id in raw_value.split(",")
                if user_id.strip().isdigit()
            }
        except ValueError as e:
            logger.error("Error parsing %s: %s", env_name, e)
        return ids

    def is_super_admin(self, user_id: int) -> bool:
        """Check if a user is a super admin."""
        return user_id in self.super_admin_ids

    def is_trainer_admin(self, user_id: int) -> bool:
        """Check if a user is a trainer admin."""
        return user_id in self.trainer_admin_ids

    def is_admin(self, user_id: int) -> bool:
        """Backward-compatible generic admin check."""
        return self.is_super_admin(user_id) or self.is_trainer_admin(user_id)

    def add_trainer_admin(self, user_id: int) -> bool:
        """Add a trainer admin user ID (runtime, not persistent)."""
        if user_id not in self.trainer_admin_ids:
            self.trainer_admin_ids.add(user_id)
            logger.info(f"Added trainer admin user ID: {user_id}")
            return True
        return False

    def remove_trainer_admin(self, user_id: int) -> bool:
        """Remove a trainer admin user ID (runtime, not persistent)."""
        if user_id in self.trainer_admin_ids:
            self.trainer_admin_ids.remove(user_id)
            logger.info(f"Removed trainer admin user ID: {user_id}")
            return True
        return False

    def get_all_admins(self) -> set[int]:
        """Get union of all admin user IDs."""
        return self.super_admin_ids.union(self.trainer_admin_ids)


# Global singleton used by handlers
admin_manager = AdminManager()
