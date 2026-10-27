"""Property tests. The renderer below is written independently of the parser
and its lexicon, so both cannot share the same mistaken assumption."""

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from quantity_parser import parse_quantity

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
DENOMS = {3: ("third", "thirds"), 4: ("quarter", "quarters"), 5: ("fifth", "fifths"), 6: ("sixth", "sixths"),
          7: ("seventh", "sevenths"), 8: ("eighth", "eighths"), 9: ("ninth", "ninths"), 10: ("tenth", "tenths")}


def words(n: int) -> str:
    """English for 0 <= n < 10**6."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " and " + words(n % 100))
    return words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + words(n % 1000))


def value(text, **kw):
    r = parse_quantity(text, **kw)
    assert r.status == "resolved", r
    return r.quantity.value


integers = st.integers(0, 999_999)
proper = st.integers(3, 10).flatmap(lambda d: st.tuples(st.integers(1, d - 1), st.just(d)))
whitespace = st.text(" \t\n", min_size=1, max_size=3)


@given(integers)
def test_integer_words(n):
    assert value(words(n)) == n


@given(integers)
def test_integer_digits(n):
    assert value(str(n)) == n


@given(st.integers(-10**6, 10**6), st.integers(1, 10**6))
def test_ratio_normalizes_and_round_trips(n, d):
    r = parse_quantity(f"{n}/{d}")
    expected = Fraction(n, d)
    assert r.quantity.value == expected
    v = r.to_dict()["quantity"]["value"]
    assert Fraction(v["numerator"], v["denominator"]) == expected
    assert v["denominator"] > 0


# Wholes ending in a scale word ("one hundred and two thirds") are genuinely
# ambiguous and covered in test_parser.py.
@given(st.integers(1, 999).filter(lambda n: n % 100), proper)
def test_outer_sign_negates_whole_mixed_number(whole, frac):
    n, d = frac
    fraction_words = f"{words(n)} {DENOMS[d][n != 1]}"
    positive = value(f"{words(whole)} and {fraction_words}")
    assert positive == whole + Fraction(n, d)
    assert value(f"minus {words(whole)} and {fraction_words}") == -positive
    assert value(f"-{whole} {n}/{d}") == -positive


@given(integers)
def test_percentage_is_value_over_100(n):
    for text in (words(n), str(n)):
        r = parse_quantity(f"{text} percent")
        assert r.quantity.kind == "percentage"
        assert r.quantity.value == value(text) / 100


@given(integers, whitespace, whitespace)
def test_whitespace_preserves_meaning(n, before, between):
    text = words(n).replace(" ", between)
    assert value(before + text + before) == n


@given(integers, st.sampled_from(["apples", "rows", "the", "xyz"]))
def test_unexplained_words_prevent_resolution(n, extra):
    for text in (f"{words(n)} {extra}", f"{extra} {words(n)}"):
        assert parse_quantity(text).status != "resolved"


@given(integers, whitespace, whitespace)
def test_span_covers_quantity_after_normalization(n, left, right):
    text = left + words(n) + right
    r = parse_quantity(text)
    assert text[slice(*r.span)] == words(n)
