"""MineBridge package shim.

This package provides a module entry-point while the project migrates to a
src/ layout. Core modules currently live at the repository root and are
imported here for compatibility.
"""

from importlib import import_module as _import

# Re-export commonly used modules for convenience
bot_init = _import("bot_init")
config = _import("config")
utils = _import("utils")
rag = _import("rag")
mc = _import("mc")
mb_api = _import("mb_api")
msgs = _import("msgs")
handlers_helpers = _import("handlers_helpers")
handlers = _import("handlers")

__all__ = [
    "bot_init",
    "config",
    "utils",
    "rag",
    "mc",
    "mb_api",
    "msgs",
    "handlers_helpers",
    "handlers",
]

