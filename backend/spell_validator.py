import logging
import random

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    InputTransportMessageFrame,
    InterruptionFrame,
    OutputTransportMessageFrame,
    TextFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameProcessor

from words import WORDS_POOL

logging.basicConfig(
    filename="spellbee.log",
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger("spellbee")


class SpellBeeValidator(FrameProcessor):

    def __init__(self, max_rounds: int = 5) -> None:
        super().__init__()

        self.max_rounds: int = max_rounds
        self.score: int = 0
        self.rounds_played: int = 0
        self.current_word: str = ""
        self.used_words: set[str] = set()

        self._buffer: str = ""
        self._game_started: bool = False
        self._waiting_to_start: bool = True
        self._waiting_for_answer: bool = False
        self._bot_is_speaking: bool = False

    async def process_frame(self, frame, direction) -> None:
        await super().process_frame(frame, direction)

        log.debug(f"FRAME: {type(frame).__name__} | game_started={self._game_started} waiting_for_answer={self._waiting_for_answer} bot_speaking={self._bot_is_speaking} buffer={self._buffer!r}")

        if isinstance(frame, InputTransportMessageFrame):
            await self._handle_app_message(frame)

        elif isinstance(frame, TranscriptionFrame):
            await self._handle_transcription(frame)
            return  

        elif isinstance(frame, UserStoppedSpeakingFrame):
            await self._handle_user_stopped_speaking(frame, direction)

        elif isinstance(frame, BotStartedSpeakingFrame):
            self._bot_is_speaking = True
            await self.push_frame(frame, direction)

        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_is_speaking = False
            await self.push_frame(frame, direction)

        elif isinstance(frame, UserStartedSpeakingFrame):
            await self._handle_user_started_speaking(frame, direction)

        elif isinstance(frame, InterruptionFrame):
            self._bot_is_speaking = False
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _handle_app_message(self, frame: InputTransportMessageFrame) -> None:
        payload = getattr(frame, "message", getattr(frame, "payload", {}))
        if isinstance(payload, dict) and "data" in payload:
            payload = payload["data"]

        action = payload.get("action")
        log.debug(f"APP MESSAGE: action={action}")

        if action == "start_game" and self._waiting_to_start:
            self._waiting_to_start = False
            await self._start_game()

        elif action == "skip_word" and self._game_started:
            self._buffer = ""
            self._waiting_for_answer = False
            await self._advance_round(feedback="Okay, moving on.")

    async def _handle_transcription(self, frame: TranscriptionFrame) -> None:
        log.debug(f"TRANSCRIPTION: text={frame.text!r} waiting={self._waiting_for_answer}")
        if not (self._game_started and self._waiting_for_answer):
            return

        token = frame.text.strip().lower().replace(".", "").replace(" ", "")
        if token:
            self._buffer += token
            log.debug(f"BUFFER: {self._buffer!r}")

    async def _handle_user_stopped_speaking(self, frame, direction) -> None:
        log.debug(f"USER STOPPED SPEAKING: buffer={self._buffer!r} waiting={self._waiting_for_answer}")
        if self._game_started and self._waiting_for_answer and self._buffer:
            await self._grade_current_buffer()
        await self.push_frame(frame, direction)

    async def _handle_user_started_speaking(self, frame, direction) -> None:
        log.debug(f"USER STARTED SPEAKING: bot_speaking={self._bot_is_speaking}")
        if self._bot_is_speaking and self._game_started:
            log.debug("INTERRUPTION: re-announcing current word")
            self._buffer = ""
            self._waiting_for_answer = False
            await self._re_announce_current_word()
        await self.push_frame(frame, direction)

    async def _start_game(self) -> None:
        self.current_word = self._pick_word()
        self._game_started = True
        log.debug(f"GAME START: first word={self.current_word!r}")
        prompt = f"Hello! Let's play Spell Bee. Your first word is {self.current_word}. Please spell it now."
        await self.push_frame(TextFrame(prompt))
        self._waiting_for_answer = True

    async def _grade_current_buffer(self) -> None:
        if not self._waiting_for_answer:
            return

        attempt = self._buffer.strip()
        log.debug(f"GRADING: attempt={attempt!r} correct={self.current_word!r}")

        self._waiting_for_answer = False
        self._buffer = ""

        correct = attempt == self.current_word
        if correct:
            self.score += 1

        feedback = "That is correct!" if correct else f"Incorrect. The word was {self.current_word}."
        log.debug(f"RESULT: correct={correct} score={self.score}")
        await self._advance_round(feedback=feedback)

    async def _advance_round(self, feedback: str) -> None:
        self.rounds_played += 1
        log.debug(f"ADVANCE ROUND: round={self.rounds_played}/{self.max_rounds}")

        await self.push_frame(OutputTransportMessageFrame({
            "type": "score_update",
            "score": self.score,
            "wordCount": self.rounds_played,
        }))

        if self.rounds_played < self.max_rounds:
            self.current_word = self._pick_word()
            utterance = f"{feedback} Your next word is {self.current_word}. Please spell {self.current_word}."
            log.debug(f"NEXT WORD: {self.current_word!r}")
            await self.push_frame(TextFrame(utterance))
            self._waiting_for_answer = True
        else:
            final = f"{feedback} Game over! You scored {self.score} out of {self.max_rounds}. Well done!"
            log.debug("GAME OVER")
            await self.push_frame(TextFrame(final))
            await self.push_frame(EndFrame())

    async def _re_announce_current_word(self) -> None:
        utterance = f"Sorry, let me repeat that. Your word is {self.current_word}. Please spell {self.current_word}."
        await self.push_frame(TextFrame(utterance))
        self._waiting_for_answer = True

    def _pick_word(self) -> str:
        available = [w for w in WORDS_POOL if w not in self.used_words]
        if not available:
            self.used_words.clear()
            available = list(WORDS_POOL)
        word = random.choice(available)
        self.used_words.add(word)
        return word