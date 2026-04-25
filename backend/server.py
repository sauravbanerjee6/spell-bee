"""
server.py

Lightweight FastAPI server that acts as the orchestration layer.

Responsibilities
----------------
- Spawn the bot process automatically on startup (via lifespan).
- Serve the static frontend (frontend/index.html).
- Expose a POST /start-bot endpoint to manually spawn additional bot processes
  (useful for multi-room scenarios or restarting a crashed bot).
- Health-check endpoint for load-balancer / uptime monitoring.

Run
---
    uvicorn server:app --host 0.0.0.0 --port 8000

    NOTE: Avoid --reload in production; it restarts the server on every file
    save, which spawns a new bot process each time.

Environment variables (set in .env)
------------------------------------------------------------
    DAILY_ROOM_URL      - Room URL the bot should join on startup.
    DEEPGRAM_API_KEY    - Forwarded to the bot subprocess.
"""

import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

# Resolve paths relative to this file's real location on disk.
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
BOT_SCRIPT = BASE_DIR / "bot.py"


def _spawn_bot(room_url: str, bot_token: str = "") -> subprocess.Popen:
    """Launch bot.py as an independent subprocess and return the handle."""
    env = {**os.environ, "DAILY_ROOM_URL": room_url}
    if bot_token:
        env["DAILY_BOT_TOKEN"] = bot_token

    return subprocess.Popen(
        [sys.executable, str(BOT_SCRIPT)],
        env=env,
        # Detach so the bot outlives a server restart.
        start_new_session=True,
    )


# ---------------------------------------------------------------------------
# Lifespan — runs once on startup and once on shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    room_url = os.getenv("DAILY_ROOM_URL", "")
    if room_url:
        proc = _spawn_bot(room_url)
        print(f"🤖 Bot spawned (PID {proc.pid}) for room: {room_url}")
    else:
        print("⚠️  DAILY_ROOM_URL not set — bot was NOT started automatically.")
    yield
    # Shutdown hook — add cleanup here if needed (e.g. SIGTERM to bot PIDs).


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Spell Bee Bot Server", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_frontend() -> FileResponse:
    """Serve the game UI."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Manual bot spawn (multi-room / restart use-case)
# ---------------------------------------------------------------------------

class StartBotRequest(BaseModel):
    room_url: str = ""   # Falls back to DAILY_ROOM_URL if omitted.
    bot_token: str = ""  # Optional Daily meeting token for private rooms.


@app.post("/start-bot")
async def start_bot(body: StartBotRequest) -> JSONResponse:
    """
    Spawn an additional bot subprocess for the given room.
    Each bot runs in its own process — no shared in-memory state.
    """
    room_url = body.room_url or os.getenv("DAILY_ROOM_URL", "")
    if not room_url:
        raise HTTPException(
            status_code=400,
            detail="room_url must be provided in the request body or via DAILY_ROOM_URL.",
        )

    try:
        proc = _spawn_bot(room_url, bot_token=body.bot_token)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {exc}") from exc

    return JSONResponse({"status": "started", "pid": proc.pid, "room_url": room_url})