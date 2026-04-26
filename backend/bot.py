import asyncio
import os

from dotenv import load_dotenv
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_turn_processor import UserTurnProcessor

from spell_validator import SpellBeeValidator

load_dotenv()


async def run_bot(room_url: str, bot_token: str | None = None) -> None:
    transport = DailyTransport(
        room_url=room_url,
        token=bot_token,
        bot_name="SpellBee Bot",
        params=DailyParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
        ),
    )

    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer())
    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
    turn = UserTurnProcessor()
    tts = DeepgramTTSService(
        api_key=os.environ["DEEPGRAM_API_KEY"],
        settings=DeepgramTTSService.Settings(voice="aura-helios-en"),
    )

    pipeline = Pipeline([
        transport.input(),
        vad,           
        stt,           
        turn,          
        SpellBeeValidator(max_rounds=5),
        tts,
        transport.output(),
    ])

    await PipelineRunner().run(PipelineTask(pipeline, enable_rtvi=False))


if __name__ == "__main__":
    room_url = os.getenv("DAILY_ROOM_URL")
    if not room_url:
        raise EnvironmentError("DAILY_ROOM_URL is not set.")
    asyncio.run(run_bot(room_url=room_url))