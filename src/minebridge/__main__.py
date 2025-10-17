import asyncio
from importlib import import_module


def _run():
    main_mod = import_module("main")
    if hasattr(main_mod, "main"):
        asyncio.run(main_mod.main())
    else:
        raise SystemExit("minebridge: missing main.main() entrypoint")


if __name__ == "__main__":
    _run()

