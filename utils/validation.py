"""Validation utilities."""
from typing import Optional, Any


def is_valid_id(value: Any) -> bool:
    """Check if value is a valid ID (positive integer).
    
    Args:
        value: Value to check
        
    Returns:
        True if value is a valid ID
    """
    return isinstance(value, int) and value > 0


def is_valid_string(value: Any, min_length: int = 0, max_length: Optional[int] = None) -> bool:
    """Check if value is a valid non-empty string.
    
    Args:
        value: Value to check
        min_length: Minimum length (default: 0)
        max_length: Maximum length (None for no limit)
        
    Returns:
        True if value is a valid string
    """
    if not isinstance(value, str):
        return False
    
    if len(value.strip()) < min_length:
        return False
    
    if max_length is not None and len(value) > max_length:
        return False
    
    return True


def normalize_string(value: str, max_length: Optional[int] = None) -> str:
    """Normalize string value.
    
    Args:
        value: String to normalize
        max_length: Maximum length (None for no limit)
        
    Returns:
        Normalized string
    """
    if not isinstance(value, str):
        return ""
    
    normalized = value.strip()
    
    if max_length is not None and len(normalized) > max_length:
        normalized = normalized[:max_length]
    
    return normalized


def safe_get_attr(obj: Any, attr_name: str, default: Any = None) -> Any:
    """Safely get attribute from object.
    
    Args:
        obj: Object to get attribute from
        attr_name: Attribute name
        default: Default value if attribute doesn't exist
        
    Returns:
        Attribute value or default
    """
    try:
        return getattr(obj, attr_name, default)
    except Exception:
        return default


def validate_message_context(
    prompt: str,
    has_image: bool = False,
    image_bytes: Optional[bytes] = None
) -> bool:
    """Validate message context for AI completion.
    
    Args:
        prompt: User prompt
        has_image: Whether message has image
        image_bytes: Image bytes if available
        
    Returns:
        True if context is valid
    """
    if not prompt and not has_image:
        return False
    
    if has_image and not image_bytes:
        return False
    
    return True

