import random 

WORDS = [
    "acquire", "benevolent", "conscience", "diligent", "eloquent",
    "ferocious", "gracious", "harmonious", "intricate", "jubilant",
    "kaleidoscope", "luminous", "magnificent", "nourishment", "obscure",
    "peculiar", "quarantine", "resilient", "sophisticated", "tenacious",
]

def getRandomWord() -> str:
    if not WORDS:
        raise ValueError("[WORD_LIST] WORDS list is empty, cannot pick a word")
    return random.choice(WORDS)

