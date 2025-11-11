"""
FinBot Platform Main Application Entry Point
- Launches web apps and api endpoints.
"""

import uvicorn

from finbot.config import settings

if __name__ == "__main__":
    print("🚀 Starting FinBot CTF Platform")
    print(f"📍 Server will run at http://{settings.HOST}:{settings.PORT}")
    print(f"📋 Application log level: {settings.LOG_LEVEL.upper()}")

    # Note: Application logging is configured in finbot.main when the module loads
    # The log_level parameter here only controls uvicorn's own logging
    uvicorn.run(
        "finbot.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning",  # Controls uvicorn logs only
    )
