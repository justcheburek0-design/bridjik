"""Regression checks for model-visible Moscow timestamps (no network calls)."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from aiogram.types import Message

from application.services.ai import AIService
from application.services.ai_prompt_builder import AIPromptBuilderMixin
from application.services.ai_tools import register_tools
from domain.entities import Chat, MessageContext, User
from infrastructure.repositories.chat_logs import ChatLogsRepository
from presentation.handlers.messages import _save_incoming_message
from utils.time import historical_message, moscow_time


class MoscowTimeTests(unittest.TestCase):
    def test_timezone_and_midnight(self):
        stamp = datetime(2026, 11, 15, 22, 5, 9, tzinfo=timezone.utc)
        self.assertEqual(moscow_time(stamp), "2026-11-16 01:05:09 МСК (UTC+03:00)")
        self.assertEqual(moscow_time(stamp.replace(tzinfo=None)), moscow_time(stamp))

    def test_incoming_persistence_history_and_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = ChatLogsRepository(Path(directory) / "logs.json")
            msg = Message.model_validate({
                "message_id": 42, "date": 1794780309,
                "chat": {"id": 7, "type": "private"},
                "from": {"id": 8, "is_bot": False, "first_name": "Tester"},
                "text": "hello",
            })
            _save_incoming_message(repo, msg, "hello")
            row = repo.get_recent_messages(7, 1)[0]
            self.assertIn(moscow_time(msg.date), row[3])
            repo.add_message(7, "Ассистент", True, "answer", message_id=43)
            loaded = ChatLogsRepository(repo.file_path)
            self.assertEqual(loaded.get_recent_messages(7, 2), repo.get_recent_messages(7, 2))
            context = MessageContext(prompt="new", user=User(id=8), chat=Chat(id=7, type="private"))
            service = SimpleNamespace(chat_logs_repo=loaded)
            history = AIService._build_message_history(service, context, msg.model_copy(update={"message_id": 44}))
            self.assertEqual(len(history), 2)
            self.assertIn("Время сообщения:", str(history[0].parts))
            self.assertIn("Время сообщения:", str(history[1].parts))
            self.assertEqual(AIService._build_message_history(service, context, msg), [])
            self.assertIn("неизвестно", historical_message("legacy"))
            self.assertEqual(historical_message(row[3]), row[3])

    def test_prompt_and_live_clock_tool(self):
        builder = SimpleNamespace(
            _section_stickers=lambda: "", _section_chat_info=lambda ctx: "",
            _section_memories=lambda ctx: "",
        )
        prompt = AIPromptBuilderMixin._build_system_prompt(builder, "base", None)
        self.assertIn("Текущая дата и время:", prompt)
        self.assertIn("МСК (UTC+03:00)", prompt)
        tools = {}
        class Registry:
            def tool(self, fn):
                tools[fn.__name__] = fn
                return fn
        register_tools(Registry())
        value = asyncio.run(tools["get_current_time"](None))
        self.assertIn("МСК (UTC+03:00)", value)


if __name__ == "__main__":
    unittest.main()
