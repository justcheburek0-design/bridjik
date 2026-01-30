"""Keyboard builders."""

from html import escape

from aiogram import types

from utils.text import get_hour_string


class KeyboardBuilder:
    """Builder for inline keyboards."""

    def __init__(self, channel: str, support_url: str, donate_url: str):
        self.channel = channel
        self.support_url = support_url
        self.donate_url = donate_url

    def subscription_keyboard(self) -> types.InlineKeyboardMarkup:
        """Build subscription check keyboard."""
        return types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="Подписаться", url=f"https://t.me/{self.channel.lstrip('@')}"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="Проверить подписку", callback_data="check_subscription"
                    )
                ],
            ]
        )

    def freeze_keyboard(
        self, user_id: int, freeze_options: tuple, hot: bool = True
    ) -> types.InlineKeyboardMarkup:
        """Build freeze/unfreeze keyboard."""
        buttons = [
            types.InlineKeyboardButton(
                text=get_hour_string(hours), callback_data=f"freeze:{user_id}:{hours}"
            )
            for hours in freeze_options
        ]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]

        if hot:
            rows.append(
                [
                    types.InlineKeyboardButton(
                        text="🔥 Разморозка 🔥", callback_data=f"unfreeze:{user_id}"
                    )
                ]
            )

        return types.InlineKeyboardMarkup(inline_keyboard=rows)

    def support_keyboard(self) -> types.InlineKeyboardMarkup:
        """Build support keyboard."""
        return types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="Техподдержка", url=self.support_url)]
            ]
        )

    def donate_keyboard(self) -> types.InlineKeyboardMarkup:
        """Build donate keyboard."""
        return types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="Купить мостики", url=self.donate_url)]
            ]
        )

    def game_keyboard(self, active: bool = False) -> types.InlineKeyboardMarkup:
        """Build game keyboard."""
        rows = [[types.InlineKeyboardButton(text="Кто я?", callback_data="game:guess_object")]]
        if active:
            rows.append(
                [
                    types.InlineKeyboardButton(
                        text="Остановить игру", callback_data="game:guess_stop"
                    )
                ]
            )
        return types.InlineKeyboardMarkup(inline_keyboard=rows)
