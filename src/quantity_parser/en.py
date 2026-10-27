"""English lexicon. Word lists feed both the grammar and the evaluator."""

from fractions import Fraction

UNITS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SCALES = ["hundred", "thousand", "million", "billion"]  # text2num 3.1.0 rejects "trillion"
CARDINALS = UNITS + TENS + SCALES
DIGITS = {w: i for i, w in enumerate(UNITS[:10])}

# Explicit table: ordinals are never derived by stripping suffixes from arbitrary words.
ORDINAL_TO_CARDINAL = {
    "first": "one", "second": "two", "third": "three", "fourth": "four", "fifth": "five",
    "sixth": "six", "seventh": "seven", "eighth": "eight", "ninth": "nine", "tenth": "ten",
    "eleventh": "eleven", "twelfth": "twelve",
    **{u + "th": u for u in UNITS[13:]},             # thirteenth .. nineteenth
    **{t[:-1] + "ieth": t for t in TENS},            # twentieth .. ninetieth
    **{s + "th": s for s in SCALES},                 # hundredth .. billionth
}

# Denominator words. "first"/"second" are only valid inside compounds
# ("three twenty-firsts"); the evaluator rejects them on their own.
IRREGULAR_DENOMINATORS = {"half": 2, "quarter": 4}
PLURAL_TO_SINGULAR = {
    "halves": "half",
    "quarters": "quarter",
    **{o + "s": o for o in ORDINAL_TO_CARDINAL},
}
DENOMINATORS = [*IRREGULAR_DENOMINATORS, *ORDINAL_TO_CARDINAL, *PLURAL_TO_SINGULAR]

MULTIPLIERS = {
    **{w: Fraction(n) for w, n in {"once": 1, "twice": 2, "thrice": 3, "double": 2, "triple": 3, "quadruple": 4}.items()},
    # Bare "halves" is the verb; "three halves" still parses as the fraction 3/2.
    **dict.fromkeys(["halve", "halves", "halved", "halving"], Fraction(1, 2)),
}


def _alts(words) -> str:
    return " | ".join(f'"{w}"' for w in words)


GRAMMAR_RULES = f"""
card_word: {_alts(CARDINALS)}
scale_word: {_alts(SCALES)}
digit_word: {_alts(DIGITS)}
ord_word: {_alts(ORDINAL_TO_CARDINAL)}
denom_word: {_alts(DENOMINATORS)}
mult_word: {_alts(MULTIPLIERS)}
"""
