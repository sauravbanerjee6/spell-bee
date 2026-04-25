"""
words.py

Maintains the pool of words used in the Spell Bee game.
Keeping this isolated makes it trivial to swap in a database-backed
or difficulty-tiered word list later without touching game logic.
"""

WORDS_POOL: list[str] = [
    "rhythm", "silhouette", "conscientious", "mnemonic", "aesthetic",
    "accommodation", "broccoli", "deductible", "embarrass", "fluorescent",
    "hierarchy", "indict", "jewelry", "liaison", "millennium",
    "occurrence", "pharaoh", "questionnaire", "scherenschnitte", "vacuum",
]