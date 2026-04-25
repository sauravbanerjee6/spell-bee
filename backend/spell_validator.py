"""
spell_validator.py

Core game-logic FrameProcessor for the Spell Bee bot.
Sits in the Pipecat pipeline between STT and TTS:

    transport.input() → STT → SpellBeeValidator → TTS → transport.output()

Responsibilities
----------------
- Reacts to app-messages from the frontend (start_game, submit_spelling, skip_word).
- Accumulates transcription fragments into a per-round buffer.
- Grades the buffer on submit, pushes score updates to the frontend via
  OutputTransportMessageFrame, and drives the conversation with TextFrames.
- Ends the pipeline cleanly with EndFrame after max_rounds are exhausted.
"""

import random

from pipecat.frames.frames import (
    TextFrame,
    EndFrame,
    TranscriptionFrame,
    InputTransportMessageFrame,
    OutputTransportMessageFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameProcessor

from words import WORDS_POOL


class SpellBeeValidator(FrameProcessor):
    """Stateful frame processor that manages one full Spell Bee game session."""

    def __init__(self, max_rounds: int = 5) -> None:
        super().__init__()

        self.max_rounds: int = max_rounds
        self.score: int = 0
        self.rounds_played: int = 0
        self.current_word: str = ""
        self.used_words: set[str] = set()

        # Buffer that accumulates live transcription fragments within a round.
        self._buffer: str = ""

        # State flags
        self._game_started: bool = False
        self._waiting_to_start: bool = True
        self._waiting_for_answer: bool = False

    # ------------------------------------------------------------------
    # Public pipeline entry-point
    # ------------------------------------------------------------------

    async def process_frame(self, frame, direction) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputTransportMessageFrame):
            await self._handle_app_message(frame)

        elif isinstance(frame, TranscriptionFrame):
            await self._handle_transcription(frame)
            # Intentionally block transcription frames from reaching TTS.
            return

        else:
            # Pass all other frames (audio, system, etc.) straight through.
            await self.push_frame(frame, direction)

    # ------------------------------------------------------------------
    # Private handlers
    # ------------------------------------------------------------------

    async def _handle_app_message(self, frame: InputTransportMessageFrame) -> None:
        """Dispatch frontend app-messages to the appropriate game action."""
        payload = getattr(frame, "message", getattr(frame, "payload", {}))
        if isinstance(payload, dict) and "data" in payload:
            payload = payload["data"]

        action = payload.get("action")

        if action == "start_game" and self._waiting_to_start:
            print("🎮 Game Starting...")
            self._waiting_to_start = False
            await self._start_game()

        elif action == "submit_spelling" and self._game_started:
            await self._grade_current_buffer()

        elif action == "skip_word" and self._game_started:
            self._buffer = ""
            self._waiting_for_answer = False
            await self._advance_round(feedback="Okay, moving on.")

    async def _handle_transcription(self, frame: TranscriptionFrame) -> None:
        """Accumulate transcription tokens into the round buffer."""
        if not (self._game_started and self._waiting_for_answer):
            return

        # Normalise: lowercase, strip punctuation and spaces so "B-R-O-C-C-O-L-I"
        # and "broccoli" both reduce to the same comparison string.
        token = frame.text.strip().lower().replace(".", "").replace(" ", "")
        if token:
            self._buffer += token
            print(f"📥 Buffer: {self._buffer!r}")

    # ------------------------------------------------------------------
    # Game flow helpers
    # ------------------------------------------------------------------

    async def _start_game(self) -> None:
        """Pick the first word and kick off the game."""
        self.current_word = self._pick_word()
        self._game_started = True

        prompt = (
            f"Hello! Let's play Spell Bee. "
            f"Your first word is {self.current_word}. Please spell it now."
        )
        await self.push_frame(TextFrame(prompt))
        self._waiting_for_answer = True

    async def _grade_current_buffer(self) -> None:
        """Compare the accumulated buffer to the current word and advance."""
        if not self._waiting_for_answer:
            return

        attempt = self._buffer.strip()
        print(f"✅ Grading: {attempt!r} vs {self.current_word!r}")

        # Lock immediately so late-arriving transcription frames are ignored.
        self._waiting_for_answer = False
        self._buffer = ""

        correct = attempt == self.current_word
        if correct:
            self.score += 1

        feedback = (
            "That is correct!"
            if correct
            else f"Incorrect. The word was {self.current_word}."
        )
        await self._advance_round(feedback=feedback)

    async def _advance_round(self, feedback: str) -> None:
        """Increment round counter, push a score update, then either give the
        next word or end the game."""
        self.rounds_played += 1

        # Notify the frontend so it can update the scoreboard in real time.
        await self.push_frame(
            OutputTransportMessageFrame({
                "type": "score_update",
                "score": self.score,
                "wordCount": self.rounds_played,
            })
        )

        if self.rounds_played < self.max_rounds:
            self.current_word = self._pick_word()
            utterance = (
                f"{feedback} "
                f"Your next word is {self.current_word}. "
                f"Please spell {self.current_word}."
            )
            print(f"🤖 Bot: {utterance}")
            await self.push_frame(TextFrame(utterance))
            self._waiting_for_answer = True
        else:
            final = (
                f"{feedback} "
                f"Game over! You scored {self.score} out of {self.max_rounds}. "
                f"Well done!"
            )
            print(f"🏁 {final}")
            await self.push_frame(TextFrame(final))
            await self.push_frame(EndFrame())

    def _pick_word(self) -> str:
        """Return a random word from the pool, avoiding repeats within a game.
        Resets the used-set if all words have been exhausted."""
        available = [w for w in WORDS_POOL if w not in self.used_words]
        if not available:
            self.used_words.clear()
            available = list(WORDS_POOL)

        word = random.choice(available)
        self.used_words.add(word)
        return word