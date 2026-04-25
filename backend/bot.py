"""
bot.py

Assembles and runs the Pipecat pipeline for a single Spell Bee session.

Pipeline topology
-----------------
    DailyTransport.input()
        └─► DeepgramSTTService      (speech → text)
            └─► SpellBeeValidator   (game logic)
                └─► DeepgramTTSService  (text → speech)
                    └─► DailyTransport.output()

Invoked by server.py once per bot process; designed to be the only thing
running in this process so that each Daily room gets an isolated bot.
"""

import asyncio
import os

from dotenv import load_dotenv
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer

from spell_validator import SpellBeeValidator

load_dotenv()


async def run_bot(room_url: str, bot_token: str | None = None) -> None:
    """
    Build and run the full pipeline.

    Parameters
    ----------
    room_url:
        The Daily room URL the bot should join.
    bot_token:
        Optional Daily meeting token for rooms that require authentication.
    """
    transport = DailyTransport(
        room_url=room_url,
        token=bot_token,
        bot_name="SpellBee Bot",
        params=DailyParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            # Prevent the bot from being interrupted mid-sentence.
            not_interruptible=True,
        ),
    )

    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])

    tts = DeepgramTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramTTSService.Settings(voice="aura-helios-en"),
    )

    validator = SpellBeeValidator(max_rounds=5)

    pipeline = Pipeline([
        transport.input(),
        stt,
        validator,
        tts,
        transport.output(),
    ])

    task = PipelineTask(pipeline)
    runner = PipelineRunner()
    await runner.run(task)


if __name__ == "__main__":
    # Allow running the bot directly for local development:
    #   python bot.py
    room_url = os.getenv("DAILY_ROOM_URL")
    if not room_url:
        raise EnvironmentError("DAILY_ROOM_URL environment variable is not set.")

    asyncio.run(run_bot(room_url=room_url))