"""Subscription checking middleware."""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message


class SubscriptionMiddleware(BaseMiddleware):
    """Middleware for checking user subscription (if needed)."""
    
    def __init__(self, subscription_service):
        self.subscription_service = subscription_service
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Add subscription service to handler data
        data["subscription_service"] = self.subscription_service
        
        # Continue to handler
        return await handler(event, data)

