"""Error handling utilities."""

import json
import logging
from functools import wraps
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def safe_execute(
    func: Callable,
    error_message: str = "Произошла ошибка",
    default_return: Any = None,
    log_exception: bool = True,
) -> Any:
    """Safely execute a function with error handling.

    Args:
        func: Function to execute
        error_message: Error message to log
        default_return: Value to return on error
        log_exception: Whether to log exception

    Returns:
        Function result or default_return on error
    """
    try:
        return func()
    except Exception as e:
        if log_exception:
            logger.exception("%s: %s", error_message, str(e))
        return default_return


async def safe_execute_async(
    coro: Callable,
    error_message: str = "Произошла ошибка",
    default_return: Any = None,
    log_exception: bool = True,
) -> Any:
    """Safely execute an async function with error handling.

    Args:
        coro: Coroutine to execute
        error_message: Error message to log
        default_return: Value to return on error
        log_exception: Whether to log exception

    Returns:
        Coroutine result or default_return on error
    """
    try:
        return await coro()
    except Exception as e:
        if log_exception:
            logger.exception("%s: %s", error_message, str(e))
        return default_return


def handle_file_operation(
    operation: Callable, operation_name: str = "file operation", default_return: Any = None
) -> Any:
    """Handle file operations with standardized error handling.

    Args:
        operation: File operation function
        operation_name: Name of operation for logging
        default_return: Value to return on error

    Returns:
        Operation result or default_return on error
    """
    try:
        return operation()
    except FileNotFoundError:
        logger.warning("%s: file not found", operation_name)
        return default_return
    except PermissionError:
        logger.error("%s: permission denied", operation_name)
        return default_return
    except Exception as e:
        logger.exception("%s failed: %s", operation_name, str(e))
        return default_return


def handle_json_operation(
    operation: Callable, operation_name: str = "JSON operation", default_return: Any = None
) -> Any:
    """Handle JSON operations with standardized error handling.

    Args:
        operation: JSON operation function
        operation_name: Name of operation for logging
        default_return: Value to return on error

    Returns:
        Operation result or default_return on error
    """
    try:
        return operation()
    except json.JSONDecodeError as e:
        logger.error("%s: invalid JSON: %s", operation_name, str(e))
        return default_return
    except Exception as e:
        logger.exception("%s failed: %s", operation_name, str(e))
        return default_return
