"""Strict parsing: tokenize -> Lark Earley forest -> evaluate every tree -> dedupe."""

import re
from fractions import Fraction
from importlib.resources import files
from typing import NamedTuple

from lark import Lark, Token, Tree
from lark.exceptions import UnexpectedInput
from lark.visitors import CollapseAmbiguities

from . import en
from .cardinal import cardinal_value
from .models import KINDS, Form, Kind, ParseResult, Quantity

MAX_INPUT_CHARS = 256
MAX_TOKENS = 48
MAX_CANDIDATES = 64
MAX_MAGNITUDE = 10**15

_LARK = Lark(
    files(__package__).joinpath("grammar.lark").read_text() + en.GRAMMAR_RULES,
    parser="earley",
    lexer="basic",
    ambiguity="explicit",
    keep_all_tokens=True,
)
# Every literal word/symbol the grammar knows. Anything else is out of scope.
_VOCAB = frozenset(t.pattern.value for t in _LARK.terminals if t.pattern.type == "str")


class _Tok(NamedTuple):
    text: str  # normalized (lowercase, unicode minus -> "-")
    start: int  # offsets into the original string
    end: int
    numeric: bool


class _Fail(Exception):
    def __init__(self, status, reason, span=None):
        super().__init__(reason)
        self.status, self.reason, self.span = status, reason, span


class _Reject(Exception):
    """A candidate tree is semantically invalid."""


_TOKEN_RE = re.compile(
    r"(?P<num>\.?\d[\w.,]*)|(?P<word>[A-Za-z]+(?:-[A-Za-z]+)*)|(?P<sym>[%/+\-−])|(?P<space>\s+)"
)


def _tokenize(text: str) -> list[_Tok]:
    tokens, pos = [], 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise _Fail("unsupported", f"unsupported character {text[pos]!r}", (pos, pos + 1))
        s, span = m.group(), m.span()
        if m.lastgroup == "num":
            s = s.lower()
            # "2.5x" -> "2.5", "x"
            x_suffix = s.endswith("x") and len(s) > 1
            literal = s[:-1] if x_suffix else s
            if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", literal):
                literal = literal.replace(",", "")  # ponytail: en-US grouping only; other locales need Babel
            elif not re.fullmatch(r"\d+|\d*\.\d+|\d+(st|nd|rd|th)", literal):
                raise _Fail("invalid", f"malformed numeric literal {s!r}", span)
            if x_suffix:
                tokens += [_Tok(literal, span[0], span[1] - 1, True), _Tok("x", span[1] - 1, span[1], False)]
            else:
                tokens.append(_Tok(literal, *span, True))
        elif m.lastgroup == "word":
            # "twenty-five" -> "twenty", "five", each keeping its own offsets
            for part in re.finditer(r"[A-Za-z]+", s):
                tokens.append(_Tok(part.group().lower(), span[0] + part.start(), span[0] + part.end(), False))
        elif m.lastgroup == "sym":
            tokens.append(_Tok("-" if s == "−" else s, *span, False))
        pos = m.end()
    return tokens


# --- evaluation -------------------------------------------------------------


def _words(node) -> list[str]:
    if isinstance(node, Token):
        return [node.value]
    return [w for c in node.children for w in _words(c)]


def _trees(node: Tree) -> list[Tree]:
    return [c for c in node.children if isinstance(c, Tree)]


def _bounded(n: int) -> int:
    if abs(n) > MAX_MAGNITUDE:
        raise _Reject(f"limit_exceeded: magnitude above {MAX_MAGNITUDE}")
    return n


def _cardinal(words: list[str]) -> int:
    if words[0] in ("a", "an"):  # "a hundred" -> "one hundred"; grammar only allows it before a scale word
        words = ["one", *words[1:]]
    # English puts "and" only after a scale word. text2num also accepts
    # "fifty and two", which would make "fifty and two thirds" read as 52/3.
    if any(w == "and" and words[i - 1] not in en.SCALES for i, w in enumerate(words)):
        raise _Reject(f"'and' must follow a scale word: {' '.join(words)!r}")
    value = cardinal_value(tuple(words))
    if value is None:
        raise _Reject(f"not a complete cardinal phrase: {' '.join(words)!r}")
    return _bounded(value)


def _integer(node: Tree) -> int:
    child = node.children[0]
    return _bounded(int(child)) if isinstance(child, Token) else _cardinal(_words(child))


def _denominator(node: Tree) -> tuple[int, bool]:
    """Returns (denominator, is_plural)."""
    *prefix, last = _words(node)
    singular = en.PLURAL_TO_SINGULAR.get(last, last)
    plural = singular != last
    if singular in en.IRREGULAR_DENOMINATORS:
        if prefix:
            raise _Reject(f"{last!r} does not take a cardinal prefix")
        return en.IRREGULAR_DENOMINATORS[singular], plural
    if not prefix and singular in ("first", "second"):
        raise _Reject(f"{last!r} is not a denominator")
    return _cardinal([*prefix, en.ORDINAL_TO_CARDINAL[singular]]), plural


def _fraction(numerator: int, denominator: int) -> Fraction:
    if denominator == 0:
        raise _Reject("zero denominator")
    return Fraction(numerator, denominator)


_FORMS: dict[str, Form] = {
    "integer": "integer",
    "decimal": "decimal",
    "word_fraction": "fraction",
    "article_fraction": "fraction",
    "bare_half": "fraction",
    "ratio": "fraction",
    "mixed": "mixed_number",
    "digit_mixed": "mixed_number",
}


def _numeric(node: Tree) -> Fraction:
    match node.data:
        case "integer":
            return Fraction(_integer(node))
        case "decimal":
            if isinstance(node.children[0], Token) and node.children[0].type == "DEC":
                return Fraction(node.children[0].value)
            whole = [t for t in _trees(node) if t.data == "cardinal"]
            digits = "".join(str(en.DIGITS[_words(t)[0]]) for t in _trees(node) if t.data == "digit_word")
            return Fraction(f"{_cardinal(_words(whole[0])) if whole else 0}.{digits}")
        case "word_fraction":
            numerator_node, denom_node = _trees(node)
            numerator = _integer(numerator_node)
            denominator, plural = _denominator(denom_node)
            if plural == (numerator == 1):  # "one third", "three thirds"; not "one thirds", "three third"
                raise _Reject("numerator and denominator disagree in number")
            return _fraction(numerator, denominator)
        case "article_fraction":
            denominator, plural = _denominator(_trees(node)[1])
            if plural:
                raise _Reject("article with a plural denominator")
            return _fraction(1, denominator)
        case "bare_half":
            return Fraction(1, 2)
        case "ratio":
            numerator_node, _, denom_node = _trees(node)
            return _fraction(_integer(numerator_node), _integer(denom_node))
        case "mixed" | "digit_mixed":
            if node.data == "mixed":
                whole_node, frac_node = _trees(node)
                whole, frac = _integer(whole_node), _numeric(frac_node)
            else:
                whole, num, den = (int(t) for t in node.children if t.type == "INT")
                whole, frac = _bounded(whole), _fraction(_bounded(num), _bounded(den))
            if not 0 < frac < 1:
                raise _Reject("mixed number needs a proper fraction")
            return whole + frac
    raise AssertionError(f"unhandled node {node.data}")


def _signed(node: Tree) -> tuple[Fraction, Form]:
    """Evaluates `sign? value` children of number/percentage."""
    sign, value = 1, None
    for child in _trees(node):
        if child.data in ("neg", "pos"):
            sign = -1 if child.data == "neg" else 1
        elif child.data in _FORMS:
            value = child
    return sign * _numeric(value), _FORMS[value.data]


def _ordinal(node: Tree) -> int:
    child = node.children[0]
    if isinstance(child, Token) and child.type == "ORD_LIT":
        n, suffix = int(child[:-2]), child[-2:]
        expected = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        if n == 0 or suffix != expected:
            raise _Reject(f"malformed ordinal {child.value!r}")
        return _bounded(n)
    *prefix, last = _words(node)
    return _cardinal([*prefix, en.ORDINAL_TO_CARDINAL[last]])


def _evaluate(tree: Tree) -> Quantity:
    node = tree.children[0]
    kind: Kind = str(node.data)  # Lark rule names are Token subclasses
    if kind == "number":
        return Quantity(*_signed(node), kind)
    if kind == "percentage":
        value, form = _signed(node)
        return Quantity(value / 100, form, kind)
    if kind == "multiplier":
        first = _trees(node)[0]
        if first.data == "mult_word":
            value = en.MULTIPLIERS[_words(first)[0]]
            return Quantity(value, "integer" if value.denominator == 1 else "fraction", kind)
        return Quantity(_numeric(first), _FORMS[first.data], kind)
    return Quantity(Fraction(_ordinal(node)), "ordinal", kind)


# --- public API -------------------------------------------------------------


def parse_quantity(text: str, language: str = "en", expected_kind: Kind | None = None) -> ParseResult:
    """Parse the *whole* of `text` as one quantity. Never guesses.

    Statuses:
      resolved     exactly one interpretation survives
      ambiguous    several incompatible interpretations survive (see .interpretations)
      unsupported  out of scope: unknown word, other language, no reading of expected_kind
      invalid      in-vocabulary but malformed: incomplete phrase, zero denominator, limits

    Backend failures other than "not a cardinal" raise; they are not user-input errors.
    """
    if expected_kind is not None and expected_kind not in KINDS:
        raise ValueError(f"expected_kind must be one of {KINDS}")
    if language != "en":
        return ParseResult("unsupported", text, reason=f"language {language!r} is not supported")
    if len(text) > MAX_INPUT_CHARS:
        return ParseResult("invalid", text, reason=f"limit_exceeded: input above {MAX_INPUT_CHARS} characters")

    try:
        tokens = _tokenize(text)
        if not tokens:
            raise _Fail("invalid", "empty input")
        span = (tokens[0].start, tokens[-1].end)
        if len(tokens) > MAX_TOKENS:
            raise _Fail("invalid", f"limit_exceeded: more than {MAX_TOKENS} tokens", span)
        for t in tokens:
            if not t.numeric and t.text not in _VOCAB:
                raise _Fail("unsupported", f"unknown word {t.text!r}", (t.start, t.end))
        try:
            forest = _LARK.parse(" ".join(t.text for t in tokens))
        except UnexpectedInput:
            raise _Fail("invalid", "incomplete or malformed phrase: no complete parse", span)
        # ponytail: expands the full forest; token cap keeps it small. Prune lazily if the grammar grows.
        trees = CollapseAmbiguities().transform(forest)
        if len(trees) > MAX_CANDIDATES:
            raise _Fail("invalid", f"limit_exceeded: more than {MAX_CANDIDATES} parse trees", span)
    except _Fail as f:
        return ParseResult(f.status, text, span=f.span, reason=f.reason)

    accepted: dict[Quantity, None] = {}  # ordered set
    rejections: dict[str, None] = {}
    for tree in trees:
        try:
            accepted[_evaluate(tree)] = None
        except _Reject as r:
            rejections[str(r)] = None

    if not accepted:
        return ParseResult("invalid", text, span=span, reason="; ".join(rejections))
    candidates = [q for q in accepted if expected_kind in (None, q.kind)]
    if not candidates:
        found = ", ".join(sorted({q.kind for q in accepted}))
        return ParseResult("unsupported", text, span=span, reason=f"no {expected_kind} reading (found: {found})")
    if len(candidates) > 1:
        return ParseResult("ambiguous", text, span=span, reason="multiple interpretations", interpretations=tuple(candidates))
    return ParseResult("resolved", text, quantity=candidates[0], span=span)
