import asyncio
import os
import traceback
import json
import sys
from fastapi import WebSocket
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.frames.frames import LLMRunFrame, BotSpeakingFrame, UserSpeakingFrame, LLMFullResponseStartFrame
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMContext,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from dotenv import load_dotenv

from spell_validator import SpellBeeValidator, SpellingResultFrame
from word_list import getRandomWord

load_dotenv()

try:
    # Ensure prints are visible immediately under uvicorn reload workers.
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

def _preview_payload(payload, max_len=220):
    try:
        text = json.dumps(payload, ensure_ascii=True)
    except Exception:
        text = str(payload)
    return text[:max_len] + ("..." if len(text) > max_len else "")


def _log_context_messages(context, label):
    try:
        messages = list(getattr(context, "messages", []) or [])
        print(f"[BOT][{label}] context_count={len(messages)}", flush=True)
        for idx, msg in enumerate(messages):
            if not isinstance(msg, dict):
                print(
                    f"[BOT][{label}] context[{idx}] INVALID_TYPE={type(msg).__name__} value={_preview_payload(msg)}",
                    flush=True,
                )
                continue
            role = msg.get("role", "<missing-role>")
            has_content = "content" in msg
            content_type = type(msg.get("content")).__name__ if has_content else "<missing>"
            print(
                f"[BOT][{label}] context[{idx}] role={role} has_content={has_content} content_type={content_type}",
                flush=True,
            )
            if not has_content:
                print(
                    f"[BOT][{label}] context[{idx}] FULL_MESSAGE={_preview_payload(msg, max_len=500)}",
                    flush=True,
                )
    except Exception as e:
        print(f"[BOT][{label}] failed to inspect context: {e!r}", flush=True)
        traceback.print_exc()


async def runBot(websocket: WebSocket):
    print(f"[BOT] Initializing pipeline from {__file__}", flush=True)

    try:
        transport = FastAPIWebsocketTransport(
            websocket=websocket,
            params=FastAPIWebsocketParams(
                audio_out_enabled=True,
                add_wav_header=True,
                vad_enabled=True,
                vad_analyzer=SileroVADAnalyzer(),
                vad_audio_passthrough=True,
            )
        )
    except Exception as e:
        print(f"[BOT] Failed to initialize transport: {e}")
        return

    try:
        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))
        tts = DeepgramTTSService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            settings=DeepgramTTSService.Settings(voice="aura-asteria-en")
        )
        
        # 1. ADD SYSTEM INSTRUCTION HERE
        # 2. SET THINKING TO MINIMAL FOR LATENCY (GEMINI 3+)
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.1-8b-instant"
        )
        
    except Exception as e:
        print(f"[BOT] Failed to initialize services: {e}")
        traceback.print_exc()
        return

    validator = SpellBeeValidator()
    
    # Context should be empty or only contain conversation history (not system prompts)
    context = LLMContext() 
    context.add_message({
        "role": "system",
        "content": (
            "You are a friendly Spell Bee host. "
            "When given a SpellingResult, respond with short encouraging feedback. "
            "Say 'Correct!' or 'Sorry, the correct spelling is X.' "
            "Keep responses under 2 sentences."
        )
    })
    contextAggregatorPair = LLMContextAggregatorPair(context)

    userResponse = contextAggregatorPair.user()
    assistantResponse = contextAggregatorPair.assistant()

    pipeline = Pipeline([
        transport.input(),
        stt,
        userResponse,
        validator,
        llm,
        assistantResponse,
        tts,
        transport.output(),
    ])
    
    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
        idle_timeout_secs=60,
        idle_timeout_frames=(
            BotSpeakingFrame,
            UserSpeakingFrame,
            LLMFullResponseStartFrame,  # ← reset timer when LLM starts responding
        )
    )

    wordCount = 0

    @transport.event_handler("on_client_connected")
    async def onClientConnected(transport, client):
        print("[BOT] Client connected, starting game", flush=True)
        try:
            print("[BOT][on_client_connected] step=1 selecting word", flush=True)
            word = getRandomWord()
            print("====", word, flush=True)
            validator.setWord(word)
            print("hello")
            print(f"[BOT][on_client_connected] step=1 done word='{word}'", flush=True)
            
            # Use 'user' role for the start command
            initial_messages = [
                {"role": "user", "content": f"Start the game. The word to spell is: '{word}'. Tell the user to spell it."}
            ]
            print(
                "[BOT][on_client_connected] step=2 built initial_messages "
                f"type={type(initial_messages).__name__} len={len(initial_messages)} "
                f"preview={_preview_payload(initial_messages)}"
            )

            print(
                "[BOT][on_client_connected] step=3 add context message "
                f"payload_type={type(initial_messages).__name__}"
            )
            context.add_message(initial_messages[0])
            print("[BOT][on_client_connected] step=3 done")
            
            # Queue the messages and the context frame
            queued_messages = initial_messages
            print(
                "[BOT][on_client_connected] step=4 queue frames "
                f"queued_messages_type={type(queued_messages).__name__} "
                f"first_item_type={type(queued_messages[0]).__name__} "
                f"preview={_preview_payload(queued_messages)}"
            )
            _log_context_messages(context, "on_client_connected_before_queue")
            await task.queue_frames([LLMRunFrame()])
            print("[BOT][on_client_connected] step=4 done queued successfully")

        except Exception as e:
            print(f"[BOT] Error starting game: {e!r}")
            traceback.print_exc()

    @task.event_handler("on_frame_pushed")
    async def onFrame(frame):
        nonlocal wordCount
        if isinstance(frame, SpellingResultFrame):
            wordCount += 1
            
            try:
                print(
                    "[BOT][on_frame_pushed] step=1 received SpellingResultFrame "
                    f"wordCount={wordCount} score={frame.score} correct={frame.correct}"
                )
                print("[BOT][on_frame_pushed] step=2 sending score_update websocket message")
                await websocket.send_json({
                    "type": "score_update",
                    "score": frame.score,
                    "wordCount": wordCount,
                    "lastWord": frame.expected_word,
                    "correct": frame.correct
                })
                print("[BOT][on_frame_pushed] step=2 done")
                
                print("[BOT][on_frame_pushed] step=3 selecting next word")
                nextWord = getRandomWord()
                validator.setWord(nextWord)
                print(f"[BOT][on_frame_pushed] step=3 done nextWord='{nextWord}'")
                
                # Format the prompt for the LLM feedback
                feedback_prompt = [
                    {"role": "user", "content": (
                        f"User spelled '{frame.user_spelling}'. "
                        f"Correct answer: '{frame.expected_word}'. "
                        f"{'Correct!' if frame.correct else 'Wrong.'} "
                        f"Current score: {frame.score}. "
                        f"Now give feedback and tell them the next word: '{nextWord}'."
                    )}
                ]
                print(
                    "[BOT][on_frame_pushed] step=4 built feedback_prompt "
                    f"type={type(feedback_prompt).__name__} len={len(feedback_prompt)} "
                    f"preview={_preview_payload(feedback_prompt)}"
                )
                
                print("[BOT][on_frame_pushed] step=5 queueing feedback frames")
                _log_context_messages(context, "on_frame_pushed_before_queue")
                context.add_message(feedback_prompt[0])
                await task.queue_frames([LLMRunFrame()])
                print("[BOT][on_frame_pushed] step=5 done queued successfully")
            except Exception as e:
                print(f"[BOT] Error in feedback loop: {e!r}")
                traceback.print_exc()

    try:
        runner = PipelineRunner()
        await runner.run(task)
    except Exception as e:
        print(f"[BOT] Pipeline crashed: {e!r}")
        traceback.print_exc()