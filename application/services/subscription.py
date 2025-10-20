"""Subscription service."""
import logging
from aiogram import types, Bot

from core.exceptions import SubscriptionRequiredError


class SubscriptionService:
    """Service for checking user subscriptions."""
    
    def __init__(self, bot: Bot, channel: str):
        self.bot = bot
        self.channel = channel
    
    async def is_subscribed(self, user_id: int) -> bool:
        """Check if user is subscribed to required channel."""
        try:
            member = await self.bot.get_chat_member(chat_id=self.channel, user_id=user_id)
            return member.status in ("creator", "administrator", "member", "restricted")
        except Exception:
            logging.exception("Error checking subscription")
            return False
    
    async def send_subscription_prompt(self, message: types.Message) -> None:
        """Send subscription request with keyboard."""
        kb = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="Подписаться", url=f"https://t.me/{self.channel.lstrip('@')}")],
            [types.InlineKeyboardButton(text="Проверить подписку", callback_data="check_subscription")]
        ])
        await message.answer(
            "Для доступа нужен канал @MineBridgeOfficial — подпишитесь и нажмите «<b>Проверить подписку</b>»",
            reply_markup=kb
        )

