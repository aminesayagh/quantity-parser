import json
from fractions import Fraction
from pathlib import Path

import pytest

from quantity_parser import parse_quantity
from quantity_parser import cardinal

FIXTURES = Path(__file__).parent / "fixtures"
REQUIRED = [json.loads(line) for line in (FIXTURES / "required_examples.jsonl").read_text().splitlines()]


def check(text, status, value=None, form=None, kind=None, expected_kind=None):
    r = parse_quantity(text, expected_kind=expected_kind)
    assert r.status == status, r
    if status == "resolved":
        q = r.quantity
        assert (q.value, q.form, q.kind) == (Fraction(value), form, kind), r
    else:
        assert r.quantity is None, r  # never expose a guessed quantity
    return r


@pytest.mark.parametrize("case", REQUIRED, ids=[c["input"] for c in REQUIRED])
def test_required_examples(case):
    check(case["input"], case["status"], case.get("value"), case.get("form"), case.get("kind"), case.get("expected_kind"))


@pytest.mark.parametrize(
    "text, value, form, kind",
    [
        # literals and signs
        ("25", "25", "integer", "number"),
        ("-2.5", "-5/2", "decimal", "number"),
        ("+7", "7", "integer", "number"),
        ("−3", "-3", "integer", "number"),
        ("negative one third", "-1/3", "fraction", "number"),
        (".5", "1/2", "decimal", "number"),
        ("two point zero five", "41/20", "decimal", "number"),
        ("point five", "1/2", "decimal", "number"),
        # cardinals via text2num
        ("a hundred and twenty", "120", "integer", "number"),
        ("one million two hundred thousand", "1200000", "integer", "number"),
        ("Twenty Five", "25", "integer", "number"),
        # fractions and mixed numbers
        ("one half", "1/2", "fraction", "number"),
        ("an eighth", "1/8", "fraction", "number"),
        ("three quarters", "3/4", "fraction", "number"),
        ("3/8", "3/8", "fraction", "number"),
        ("2/4", "1/2", "fraction", "number"),
        ("2 1/2", "5/2", "mixed_number", "number"),
        ("two and 1/2", "5/2", "mixed_number", "number"),
        ("three twenty-fifths", "3/25", "fraction", "number"),
        ("seven hundredths", "7/100", "fraction", "number"),
        ("one hundred and twenty and a half", "241/2", "mixed_number", "number"),
        ("two and three quarters", "11/4", "mixed_number", "number"),
        # multipliers
        ("double", "2", "integer", "multiplier"),
        ("thrice", "3", "integer", "multiplier"),
        ("1.5 times", "3/2", "decimal", "multiplier"),
        ("17 times", "17", "integer", "multiplier"),
        ("halve", "1/2", "fraction", "multiplier"),
        ("halves", "1/2", "fraction", "multiplier"),
        ("halved", "1/2", "fraction", "multiplier"),
        ("halving", "1/2", "fraction", "multiplier"),
        ("three halves", "3/2", "fraction", "number"),  # plural denominator, not the verb
        ("2.5x", "5/2", "decimal", "multiplier"),
        ("3x", "3", "integer", "multiplier"),
        ("10X", "10", "integer", "multiplier"),
        ("3 x", "3", "integer", "multiplier"),
        ("1,500x", "1500", "integer", "multiplier"),
        # en-US digit grouping
        ("1,500", "1500", "integer", "number"),
        ("3,250", "3250", "integer", "number"),
        ("1,250.50", "2501/2", "decimal", "number"),
        ("1,000,000", "1000000", "integer", "number"),
        ("-1,500", "-1500", "integer", "number"),
        ("1,500%", "15", "integer", "percentage"),
        # percentages
        ("15%", "3/20", "integer", "percentage"),
        ("-15 %", "-3/20", "integer", "percentage"),
        ("2.5 per cent", "1/40", "decimal", "percentage"),
        ("a quarter of a percent", "1/400", "fraction", "percentage"),
        ("two and a half percent", "1/40", "mixed_number", "percentage"),
        # ordinals
        ("first", "1", "ordinal", "ordinal"),
        ("twenty first", "21", "ordinal", "ordinal"),
        ("21st", "21", "ordinal", "ordinal"),
        ("12th", "12", "ordinal", "ordinal"),
        ("hundredth", "100", "ordinal", "ordinal"),
    ],
)
def test_resolved(text, value, form, kind):
    check(text, "resolved", value, form, kind)


@pytest.mark.parametrize(
    "text, status",
    [
        ("", "invalid"),
        ("   ", "invalid"),
        ("five five", "invalid"),
        ("one thirds", "invalid"),  # number agreement
        ("three fifth", "invalid"),
        ("a thirds", "invalid"),
        ("two and three halves", "invalid"),  # mixed needs a proper fraction
        ("1/0", "invalid"),
        ("3th", "invalid"),
        ("0th", "invalid"),
        ("minus minus five", "invalid"),  # one outer sign only
        ("minus twice", "invalid"),
        ("a second", "invalid"),  # "second" alone is not a denominator
        ("5.", "invalid"),
        ("12abc", "invalid"),
        ("1,50", "invalid"),  # malformed grouping is rejected, not guessed
        ("12,3456", "invalid"),
        ("1,000,00", "invalid"),
        (",500", "unsupported"),
        ("x", "invalid"),
        ("1.2.3x", "invalid"),
        ("twice x", "invalid"),
        ("minus 3x", "invalid"),  # no signed multipliers
        ("one trillion", "unsupported"),  # beyond text2num 3.1.0
        ("twenty five apples", "unsupported"),
        ("½", "unsupported"),
        ("1" + "0" * 20, "invalid"),  # magnitude limit
        ("one " * 60, "invalid"),  # token/char limit
    ],
)
def test_rejected(text, status):
    check(text, status)


def test_ambiguity_is_reported_not_resolved():
    r = check("two hundred fifths", "ambiguous")
    assert {q.value for q in r.interpretations} == {Fraction(40), Fraction(2, 105)}
    r = check("one hundred and two thirds", "ambiguous")  # 100 2/3 or 102/3
    assert {q.value for q in r.interpretations} == {100 + Fraction(2, 3), Fraction(102, 3)}
    check("fifty and two thirds", "resolved", "152/3", "mixed_number", "number")  # "fifty and two" is not English
    r = check("one hundredth", "ambiguous")
    assert {(q.value, q.kind) for q in r.interpretations} == {(Fraction(1, 100), "number"), (Fraction(100), "ordinal")}


def test_expected_kind_filters_but_never_coerces():
    check("one hundredth", "resolved", "100", "ordinal", "ordinal", expected_kind="ordinal")
    check("one hundredth", "resolved", "1/100", "fraction", "number", expected_kind="number")
    check("third", "unsupported", expected_kind="number")
    check("twice", "unsupported", expected_kind="percentage")
    with pytest.raises(ValueError):
        parse_quantity("five", expected_kind="money")


def test_spans_point_into_original_text():
    r = parse_quantity("  Twenty-Five  ")
    assert r.span == (2, 13)
    assert parse_quantity("2.5x").span == (0, 4)
    r = parse_quantity("double room")
    assert r.status == "unsupported" and "double room"[slice(*r.span)] == "room"


def test_serialization_matches_contract():
    assert parse_quantity("two and a half times", expected_kind="multiplier").to_dict() == {
        "status": "resolved",
        "quantity": {"value": {"numerator": 5, "denominator": 2}, "form": "mixed_number", "kind": "multiplier"},
        "source": "two and a half times",
        "span": [0, 20],
        "reason": None,
    }
    assert json.dumps(parse_quantity("one hundredth").to_dict())  # ambiguous serializes too


def test_other_language_is_unsupported():
    assert parse_quantity("vingt", language="fr").status == "unsupported"


def test_backend_failure_is_operational_not_user_error(monkeypatch):
    def boom(*_):
        raise RuntimeError("backend down")

    monkeypatch.setattr(cardinal, "text2num", boom)
    cardinal.cardinal_value.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            parse_quantity("forty two")
    finally:
        cardinal.cardinal_value.cache_clear()
