import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import traceback

import bot

load_dotenv()
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.websocket("/ws")
async def websocketEndpoint(websocket: WebSocket):
    await websocket.accept()
    
    try:
        await bot.runBot(websocket)
    except WebSocketDisconnect:
        print("CLient disconnected normally!")
    except Exception as e:
        print(f"[WS] Bot error: {e}")
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass
    finally:
        print("[WS] Cleaning up connection")
        try:
            await websocket.close()
        except Exception:
            pass