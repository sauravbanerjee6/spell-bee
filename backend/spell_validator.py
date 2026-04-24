import dataclasses
import traceback
from pipecat.frames.frames import Frame, TextFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection

@dataclasses.dataclass
class WordAssignedFrame(Frame):
    word: str

@dataclasses.dataclass
class SpellingResultFrame(Frame):
    correct: bool
    user_spelling: str
    expected_word: str
    score: int

class SpellBeeValidator(FrameProcessor):

    def __init__(self):
        super().__init__()
        self._current_word: str = ""
        self._score: int = 0
        self._waiting_for_spelling: bool = False

    def setWord(self, word: str):
        if not word or not word.strip():
            print("[VALIDATOR] WARNING: setWord called with empty word, ignoring")
            return
        self._current_word = word.strip()
        self._waiting_for_spelling = True
        print(f"[VALIDATOR] New word set: '{self._current_word}'")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        try:
            await super().process_frame(frame, direction)
        except Exception as e:
            print(f"[VALIDATOR] Error in super().process_frame: {e}")
            traceback.print_exc()
            return

        try:
            if isinstance(frame, TextFrame) and self._waiting_for_spelling:

                if not self._current_word:
                    print("[VALIDATOR] WARNING: TextFrame received but no word is set, passing frame through")
                    await self.push_frame(frame, direction)
                    return

                userInput = frame.text.replace(" ", "").strip().lower()

                if not userInput:
                    print("[VALIDATOR] WARNING: Empty transcription received, ignoring")
                    return

                expected = self._current_word.lower()
                isCorrect = userInput == expected

                if isCorrect:
                    self._score += 1

                self._waiting_for_spelling = False

                print(f"[VALIDATOR] Input: '{userInput}' | Expected: '{expected}' | Correct: {isCorrect} | Score: {self._score}")

                await self.push_frame(
                    SpellingResultFrame(
                        correct=isCorrect,
                        user_spelling=userInput,
                        expected_word=expected,
                        score=self._score
                    )
                )

            else:
                await self.push_frame(frame, direction)

        except Exception as e:
            print(f"[VALIDATOR] Error processing frame: {e}")
            traceback.print_exc()
            try:
                await self.push_frame(frame, direction)
            except Exception:
                pass