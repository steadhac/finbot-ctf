"""
FinBot Platform Main Application
- Serves all the applications for the FinBot platform.
"""

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from finbot.apps.vendor.main import app as vendor_app
from finbot.apps.web.routes import router as web_router
from finbot.core.auth.csrf import CSRFProtectionMiddleware
from finbot.core.auth.middleware import SessionMiddleware, get_session_context
from finbot.core.auth.session import SessionContext, session_manager
from finbot.core.error_handlers import register_error_handlers

app = FastAPI(
    title="FinBot Platform",
    description="FinBot Application Platform",
    version="0.1.0",
)

# Add middleware - last in, first out order
# Execute session first, then CSRF
app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(SessionMiddleware)

# Register error handlers
register_error_handlers(app)

import os
from pathlib import Path

# Define the uploads directory path
UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"

# Ensure the directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount Static Files
app.mount("/static", StaticFiles(directory="finbot/static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Mount all the applications for the platform
app.mount("/vendor", vendor_app)
# Web application is mounted at the root of the platform
app.include_router(web_router)


# web agreement handler
@app.get("/agreement", response_class=HTMLResponse)
async def agreement(_: Request):
    """FinBot Agreement page"""
    try:
        # (TODO) cache this to reduce disk I/O
        with open("finbot/static/pages/agreement.html", "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content, status_code=200)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Agreement page not found") from e


# Session health check endpoint
@app.get("/api/session/status")
async def session_status(
    session_context: SessionContext = Depends(get_session_context),
):
    """Get current session status and security information"""
    return {
        "session_id": session_context.session_id[:8] + "...",
        "user_id": session_context.user_id,
        "is_temporary": session_context.is_temporary,
        "namespace": session_context.namespace,
        "security_status": session_context.get_security_status(),
        "csrf_token": session_context.csrf_token,
    }

# (TODO): add to lifecycle management
@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""

    # 1) Ensure DB exists and the user_sessions table is present
    try:
        from sqlalchemy import create_engine, text
        from finbot.config import settings

        engine = create_engine(
            settings.get_database_url(),
            **settings.get_database_config(),
        )

        # Create the user_sessions table if it's missing (safe on SQLite & Postgres)
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    session_id TEXT PRIMARY KEY,
                    namespace TEXT,
                    user_id TEXT,
                    email TEXT,
                    is_temporary BOOLEAN,
                    session_data TEXT,
                    signature TEXT,
                    user_agent TEXT,
                    last_rotation TIMESTAMP,
                    rotation_count INTEGER,
                    strict_fingerprint TEXT,
                    loose_fingerprint TEXT,
                    original_ip TEXT,
                    current_ip TEXT,
                    current_vendor_id TEXT,
                    created_at TIMESTAMP,
                    last_accessed TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """))
        print("✅ Ensured user_sessions table exists")
    except Exception as e:
        raise RuntimeError(f"Database bootstrap failed: {e}") from e

    # 2) Now it's safe to access tables
    cleaned_count = session_manager.cleanup_expired_sessions()
    if cleaned_count > 0:
        print(f"🧹 Cleaned up {cleaned_count} expired sessions on startup")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
