"""Custom exceptions for the bot."""


class BotException(Exception):
    """Base exception for bot errors."""

    pass


class SubscriptionRequiredError(BotException):
    """User is not subscribed to required channel."""

    pass


class APIError(BotException):
    """External API error."""

    pass


class PlayerNotFoundError(APIError):
    """Player not found in MineBridge API."""

    pass


class ServerUnavailableError(APIError):
    """Minecraft server is unavailable."""

    pass


class RateLimitError(APIError):
    """Rate limit exceeded."""

    pass


class ConfigurationError(BotException):
    """Configuration error."""

    pass
