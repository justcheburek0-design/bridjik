"""User service."""

from typing import Optional

from aiogram import types

from domain.entities import User
from domain.interfaces import IPsevdoRepository


class UserService:
    """Service for user-related operations."""

    def __init__(self, psevdo_repo: IPsevdoRepository):
        self.psevdo_repo = psevdo_repo

    def create_user_from_telegram(self, tg_user: types.User) -> User:
        """Create User entity from Telegram user."""
        psevdo = self.psevdo_repo.get_psevdo(tg_user.id)
        return User(
            id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            psevdo=psevdo,
            is_bot=tg_user.is_bot,
        )

    def get_display_name(self, user_id: int, tg_user: Optional[types.User] = None) -> str:
        """Get best display name for user."""
        psevdo = self.psevdo_repo.get_psevdo(user_id)
        if psevdo:
            return psevdo

        if tg_user:
            if tg_user.first_name:
                return tg_user.first_name
            if tg_user.username:
                return tg_user.username

        return "Пользователь"

    def set_psevdo(self, user_id: int, name: str) -> str:
        """Set user psevdo."""
        return self.psevdo_repo.set_psevdo(user_id, name)

    def get_psevdo(self, user_id: int) -> Optional[str]:
        """Get user psevdo."""
        return self.psevdo_repo.get_psevdo(user_id)
