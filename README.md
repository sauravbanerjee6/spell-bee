# 🐝 Spell Bee Voice Bot

A real-time voice-based Spell Bee game built with [Pipecat](https://github.com/pipecat-ai/pipecat), Daily.co, and Deepgram.

The bot speaks a word aloud, the user spells it out letter-by-letter over voice, and the bot evaluates the response — all over a live audio call.

---


## Project Structure

```
spell-bee/
├── backend/
│   ├── server.py          
│   ├── bot.py             
│   ├── spell_validator.py 
│   ├── words.py           
│   ├── requirements.txt
│   └── .env               (not committed)
└── frontend/
    └── index.html         
```

---

## How It Works

```
User microphone
     │
     ▼
Daily.co transport (audio in)
     │
     ▼
Deepgram STT  ──►  TranscriptionFrames
     │
     ▼
SpellBeeValidator (custom FrameProcessor)
  - Reacts to app-messages from frontend (start_game / submit_spelling / skip_word)
  - Accumulates transcription fragments into a per-round buffer
  - Grades the buffer on submit, pushes score_update to frontend
  - Drives conversation via TextFrames
     │
     ▼
Deepgram TTS  ──►  audio
     │
     ▼
Daily.co transport (audio out)
     │
     ▼
User speaker
```

**Turn-taking** is handled by a `_waiting_for_answer` flag inside `SpellBeeValidator`. The bot only accumulates transcription into the buffer when this flag is `True` — i.e. after it has finished speaking a word and is expecting the user's spelling. The flag is immediately set to `False` when the user submits, preventing any late-arriving transcription fragments from contaminating the next round.

**Interruption handling** is managed at the transport level via `not_interruptible=True` in `DailyParams`, combined with Silero VAD. The bot will not be cut off mid-word.

---

## Prerequisites

- Python 3.10+
- A [Daily.co](https://daily.co) account with a room created
- A [Deepgram](https://deepgram.com) account (free tier is sufficient)

---

## Setup

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd spell-bee
```

### 2. Create and activate a virtual environment

```bash
cd backend
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env`:

```env
DAILY_ROOM_URL=https://your-domain.daily.co/your-room
DEEPGRAM_API_KEY=your_deepgram_api_key_here
```

### 5. Start the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

This single command starts both the FastAPI server **and** the bot subprocess automatically. You should see:

```
INFO:     Application startup complete.
🤖 Bot spawned (PID 12345) for room: https://...
```

### 6. Open the game

Navigate to `http://localhost:8000` in your browser.

---

## Playing the Game

1. Click **Join Room** — your browser connects to the Daily room.
2. Click **Start Game** — the bot greets you and speaks the first word.
3. **Spell the word aloud** letter by letter (e.g. *"B - R - O - C - C - O - L - I"*).
4. Click **Submit Spelling** when done — the bot evaluates and gives feedback.
5. Click **Skip Word** to pass on the current word.
6. The game runs for **5 rounds**. Your final score is announced at the end.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the frontend UI |
| `GET` | `/health` | Health check |
| `POST` | `/start-bot` | Manually spawn a bot for a given room |

### POST /start-bot

```bash
curl -X POST http://localhost:8000/start-bot \
  -H "Content-Type: application/json" \
  -d '{"room_url": "https://your-domain.daily.co/your-room"}'
```

Response:
```json
{ "status": "started", "pid": 12345, "room_url": "https://..." }
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DAILY_ROOM_URL` | ✅ | Daily.co room the bot joins on startup |
| `DEEPGRAM_API_KEY` | ✅ | Used for both STT and TTS |

---

## Key Design Decisions

- **Bot runs as a subprocess** — each game session is fully isolated. A crash in one session cannot affect the server or other sessions.
- **Single pipeline process** — Pipecat's async pipeline handles the full audio loop in one process, keeping latency low.
- **No LLM used** — spelling validation is deterministic (exact string match after normalisation), so an LLM is unnecessary and would add latency.
- **Buffer accumulation** — Deepgram may return a word's spelling as multiple `TranscriptionFrame` events. The validator accumulates all fragments until `submit_spelling` is received, rather than grading on the first fragment.
