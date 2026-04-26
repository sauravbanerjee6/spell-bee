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

log = logging.getLogger("spellbee")
log.setLevel(logging.DEBUG)
log.propagate = False
_handler = logging.FileHandler("spellbee.log")
_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
log.addHandler(_handler)


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

        if action == "start_game" and self._waiting_to_start:
            self._waiting_to_start = False
            await self._start_game()

        elif action == "skip_word" and self._game_started:
            self._buffer = ""
            self._waiting_for_answer = False
            await self._advance_round(feedback="Okay, moving on.")

    async def _handle_transcription(self, frame: TranscriptionFrame) -> None:
        if not (self._game_started and self._waiting_for_answer):
            return
        token = frame.text.strip().lower().replace(".", "").replace(" ", "")
        if token:
            self._buffer += token

    async def _handle_user_stopped_speaking(self, frame, direction) -> None:
        if self._game_started and self._waiting_for_answer and self._buffer:
            await self._grade_current_buffer()
        await self.push_frame(frame, direction)

    async def _handle_user_started_speaking(self, frame, direction) -> None:
        if self._bot_is_speaking and self._game_started:
            self._buffer = ""
            self._waiting_for_answer = False
            await self._re_announce_current_word()
        await self.push_frame(frame, direction)

    async def _start_game(self) -> None:
        self.current_word = self._pick_word()
        self._game_started = True
        log.debug(f"ROUND 1 | target={self.current_word!r}")
        prompt = f"Hello! Let's play Spell Bee. Your first word is {self.current_word}. Please spell it now."
        await self.push_frame(TextFrame(prompt))
        self._waiting_for_answer = True

    async def _grade_current_buffer(self) -> None:
        if not self._waiting_for_answer:
            return

        attempt = self._buffer.strip()
        self._waiting_for_answer = False
        self._buffer = ""

        correct = attempt == self.current_word
        if correct:
            self.score += 1

        log.debug(f"ROUND {self.rounds_played + 1} | target={self.current_word!r} heard={attempt!r} correct={correct} score={self.score}")
        feedback = "That is correct!" if correct else f"Incorrect. The word was {self.current_word}."
        await self._advance_round(feedback=feedback)

    async def _advance_round(self, feedback: str) -> None:
        self.rounds_played += 1

        await self.push_frame(OutputTransportMessageFrame({
            "type": "score_update",
            "score": self.score,
            "wordCount": self.rounds_played,
        }))

        if self.rounds_played < self.max_rounds:
            self.current_word = self._pick_word()
            log.debug(f"ROUND {self.rounds_played + 1} | target={self.current_word!r}")
            utterance = f"{feedback} Your next word is {self.current_word}. Please spell {self.current_word}."
            await self.push_frame(TextFrame(utterance))
            self._waiting_for_answer = True
        else:
            log.debug(f"GAME OVER | score={self.score}/{self.max_rounds}")
            final = f"{feedback} Game over! You scored {self.score} out of {self.max_rounds}. Well done!"
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