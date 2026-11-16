"""Health check endpoint for Docker healthcheck."""

import os
from aiohttp import web


async def health_check(request):
    """Health check endpoint."""
    return web.Response(text="OK", status=200)


async def start_health_server():
    """Start health check server on configurable port."""
    port = int(os.getenv("HEALTH_PORT", "8001"))
    app = web.Application()
    app.router.add_get("/health", health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    return runner
