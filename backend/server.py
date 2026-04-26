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

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"
BOT_SCRIPT = BASE_DIR / "bot.py"


def _spawn_bot(room_url: str, bot_token: str = "") -> subprocess.Popen:
    env = {**os.environ, "DAILY_ROOM_URL": room_url}
    if bot_token:
        env["DAILY_BOT_TOKEN"] = bot_token
    return subprocess.Popen(
        [sys.executable, str(BOT_SCRIPT)],
        env=env,
        start_new_session=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    room_url = os.getenv("DAILY_ROOM_URL", "")
    proc = None
    if room_url:
        proc = _spawn_bot(room_url)
        print(f"🤖 Bot spawned (PID {proc.pid}) for room: {room_url}")
    else:
        print("⚠️  DAILY_ROOM_URL not set — bot was NOT started.")
    yield
    if proc:
        proc.terminate()
        print(f"🛑 Bot (PID {proc.pid}) terminated.")


app = FastAPI(title="Spell Bee Bot Server", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


class StartBotRequest(BaseModel):
    room_url: str = ""
    bot_token: str = ""


@app.post("/start-bot")
async def start_bot(body: StartBotRequest) -> JSONResponse:
    room_url = body.room_url or os.getenv("DAILY_ROOM_URL", "")
    if not room_url:
        raise HTTPException(status_code=400, detail="room_url is required.")

    try:
        proc = _spawn_bot(room_url, bot_token=body.bot_token)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {exc}") from exc

    return JSONResponse({"status": "started", "pid": proc.pid, "room_url": room_url})